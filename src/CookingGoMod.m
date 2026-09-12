/* =============================================================================
 *  CookingGoMod - rootless tweak for Cooking GO 1.25.03
 *  iOS 16.x / arm64 / Dopamine (ElleKit) / /var/jb/usr/lib/TweakInject/
 *
 *  Static-analysis evidence this file relies on (2026-09-12):
 *    engine   : Cocos Creator 2.4.11 / cocos2d-x lite / V8 (not Unity, not IL2CPP)
 *    scripts  : plain JS, bundled as assets/scriptBundle/index.js (775 modules)
 *    access   : window.__require("Game").default.PlayerData / .MapData
 *               window.__require("AppConst").EVENT_ID
 *               window.__require("Core").default.Event
 *
 *  Layered JS injection (payload is idempotent):
 *    +[NSData dataWithContentsOfFile:] / ...:options:error: / -initWithContentsOfFile:
 *    -[NSFileManager contentsAtPath:]
 *    +[NSString stringWithContentsOfFile:encoding:error:]
 *    fopen / fopen$DARWIN_EXTSN / open / openat / guarded_open_np /
 *    open_dprotected_np  (installed only when MSHookFunction is reachable)
 *
 *  File mailbox bridge inside the app sandbox:
 *    <sandbox>/cookingmod/  mod.json cmd.json res.json state.json probe.json
 * ========================================================================== */

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <string.h>
#import <stdlib.h>
#import <unistd.h>
#import <fcntl.h>
#import <sys/stat.h>
#import <sys/types.h>

#import "CGMBootstrap.generated.h"

#ifndef CGM_VERSION
#define CGM_VERSION @"1.0.0"
#endif

static NSString * const kCGMTargetBundle = @"com.airplanecooking.chef.kitchen.restaurant.diner";
static NSString * const kCGMRelPath      = @"assets/scriptBundle/index.js";
static NSString * const kCGMMailboxName  = @"cookingmod";
static NSString * const kCGMInjectMark   = @"\n/* ==== CookingGoMod bootstrap ==== */\n";

/* ============================== logging =================================== */

static NSMutableArray<NSString *> *gLogStore = nil;
static void (^gLogSink)(NSString *line) = nil;
static NSString *gMailboxPath = nil;

static void CGMFileAppend(NSString *line) {
    if (!gMailboxPath) { return; }
    NSString *p = [gMailboxPath stringByAppendingPathComponent:@"mod.log"];
    NSFileManager *fm = [NSFileManager defaultManager];
    if (![fm fileExistsAtPath:p]) {
        [line writeToFile:p atomically:YES encoding:NSUTF8StringEncoding error:NULL];
        return;
    }
    NSFileHandle *fh = [NSFileHandle fileHandleForWritingAtPath:p];
    if (!fh) { return; }
    @try {
        [fh seekToEndOfFile];
        [fh writeData:[(line @"\n") dataUsingEncoding:NSUTF8StringEncoding]];
    } @catch (NSException *e) {
    } @finally {
        [fh closeFile];
    }
}

static void CGMLog(NSString *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    NSString *body = [[NSString alloc] initWithFormat:fmt arguments:ap];
    va_end(ap);
    NSString *line = [NSString stringWithFormat:@"[%@] %@", [[NSDate date] description], body];
    NSLog(@"[CookingGoMod] %@", body);
    if (!gLogStore) { gLogStore = [NSMutableArray array]; }
    [gLogStore addObject:body];
    if (gLogStore.count > 400) { [gLogStore removeObjectAtIndex:0]; }
    CGMFileAppend(line);
    if (gLogSink) {
        NSString *copy = [body copy];
        dispatch_async(dispatch_get_main_queue(), ^{ gLogSink(copy); });
    }
}

/* ============================== write helpers ============================= */

static BOOL CGMWriteData(NSData *data, NSString *path) {
    if (!data || !path) { return NO; }
    NSError *err = nil;
    BOOL ok = [data writeToFile:path options:(NSDataWritingAtomic | NSDataWritingFileProtectionNone) error:&err];
    if (!ok) { CGMLog(@"write failed %@ : %@", path.lastPathComponent, err.localizedDescription); return NO; }
    chmod(path.fileSystemRepresentation, 0666);
    return YES;
}

static BOOL CGMWriteString(NSString *s, NSString *path) {
    return CGMWriteData([s dataUsingEncoding:NSUTF8StringEncoding], path);
}

static BOOL CGMWriteJSON(id obj, NSString *path) {
    if (!obj) { return NO; }
    NSError *err = nil;
    NSData *d = [NSJSONSerialization dataWithJSONObject:obj options:0 error:&err];
    if (!d) { CGMLog(@"json encode failed: %@", err.localizedDescription); return NO; }
    return CGMWriteData(d, path);
}

static id CGMReadJSON(NSString *path) {
    NSData *d = [NSData dataWithContentsOfFile:path];
    if (!d.length) { return nil; }
    NSError *err = nil;
    id o = [NSJSONSerialization JSONObjectWithData:d options:0 error:&err];
    if (!o) { return nil; }
    return o;
}

/* ============================== mailbox =================================== */

static void CGMEnsureMailbox(void) {
    NSString *home = NSHomeDirectory();
    NSArray<NSString *> *roots = @[
        home,
        [home stringByAppendingPathComponent:@"Documents"],
        [home stringByAppendingPathComponent:@"Library"],
        [home stringByAppendingPathComponent:@"tmp"],
    ];
    NSFileManager *fm = [NSFileManager defaultManager];
    for (NSString *r in roots) {
        NSString *dir = [r stringByAppendingPathComponent:kCGMMailboxName];
        [fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:NULL];
        chmod(dir.fileSystemRepresentation, 0777);
        NSString *marker = [dir stringByAppendingPathComponent:@"mod.json"];
        if (![fm fileExistsAtPath:marker]) {
            CGMWriteJSON(@{ @"bridge": @YES, @"version": CGM_VERSION, @"root": r }, marker);
        }
    }
    gMailboxPath = [home stringByAppendingPathComponent:
                        [@"Documents" stringByAppendingPathComponent:kCGMMailboxName]];
    chmod(gMailboxPath.fileSystemRepresentation, 0777);
    CGMLog(@"mailbox ready at %@", gMailboxPath);
}

/* ============================== JS injection ============================== */

static NSString *gJSPayload = nil;
static NSString *gTempScriptPath = nil;
static NSString *gSourcePath = nil;
static BOOL gInjectLogDone = NO;

static NSString *CGMSourcePath(void) {
    if (gSourcePath) { return gSourcePath; }
    NSString *p = [[[NSBundle mainBundle] bundlePath] stringByAppendingPathComponent:kCGMRelPath];
    if ([[NSFileManager defaultManager] fileExistsAtPath:p]) { gSourcePath = p; }
    else { CGMLog(@"source script not found at %@", p); }
    return gSourcePath;
}

static BOOL CGMIsTargetPath(NSString *path) {
    if (![path isKindOfClass:[NSString class]] || path.length < 8) { return NO; }
    if ([path rangeOfString:@"scriptBundle/index.js"].location != NSNotFound) { return YES; }
    return NO;
}

static BOOL CGMIsTargetPathC(const char *p) {
    if (!p) { return NO; }
    if (!strstr(p, "scriptBundle")) { return NO; }
    if (!strstr(p, "index.js")) { return NO; }
    return YES;
}

static NSData *CGMInjectedData(NSData *orig, NSString *path) {
    if (!orig.length) { return orig; }
    if (!gJSPayload.length) { return orig; }
    NSMutableData *m = [NSMutableData dataWithCapacity:orig.length + gJSPayload.length + 64];
    [m appendData:orig];
    [m appendData:[kCGMInjectMark dataUsingEncoding:NSUTF8StringEncoding]];
    [m appendData:[gJSPayload dataUsingEncoding:NSUTF8StringEncoding]];
    if (!gInjectLogDone) {
        gInjectLogDone = YES;
        CGMLog(@"JS injected through ObjC file API (%@, +%lu bytes)",
               path.lastPathComponent, (unsigned long)gJSPayload.length);
    }
    return m;
}

static NSString *CGMTempScriptPath(void) {
    if (gTempScriptPath) { return gTempScriptPath; }
    NSString *src = CGMSourcePath();
    if (!src) { return nil; }
    NSData *orig = [NSData dataWithContentsOfFile:src];
    if (!orig.length) { CGMLog(@"cannot read source script for temp copy"); return nil; }
    NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:@"cgm_bootstrap_script.js"];
    if (!CGMWriteData(orig, tmp)) { return nil; }
    gTempScriptPath = tmp;
    CGMLog(@"POSIX-level injection armoured, temp=%@ (%lu bytes)",
           tmp.lastPathComponent, (unsigned long)orig.length);
    return gTempScriptPath;
}

/* --- ObjC level hooks ----------------------------------------------------- */

static NSData *(*gOrigDataWithContentsOfFile)(id, SEL, NSString *);
static NSData *CGMDataWithContentsOfFile(id self, SEL _cmd, NSString *path) {
    NSData *d = gOrigDataWithContentsOfFile ? gOrigDataWithContentsOfFile(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    return d;
}

static NSData *(*gOrigDataWithContentsOfFileOpts)(id, SEL, NSString *, NSDataReadingOptions, NSError **);
static NSData *CGMDataWithContentsOfFileOpts(id self, SEL _cmd, NSString *path, NSDataReadingOptions opts, NSError **err) {
    NSData *d = gOrigDataWithContentsOfFileOpts ? gOrigDataWithContentsOfFileOpts(self, _cmd, path, opts, err) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    return d;
}

static id (*gOrigInitWithContentsOfFile)(id, SEL, NSString *);
static id CGMInitWithContentsOfFile(id self, SEL _cmd, NSString *path) {
    id d = gOrigInitWithContentsOfFile ? gOrigInitWithContentsOfFile(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path) && [d isKindOfClass:[NSData class]]) {
        NSData *inj = CGMInjectedData(d, path);
        if (inj != d) { return inj; }
    }
    return d;
}

static NSData *(*gOrigContentsAtPath)(id, SEL, NSString *);
static NSData *CGMContentsAtPath(id self, SEL _cmd, NSString *path) {
    NSData *d = gOrigContentsAtPath ? gOrigContentsAtPath(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    return d;
}

static NSString *(*gOrigStringContents)(id, SEL, NSString *, NSStringEncoding, NSError **);
static NSString *CGMStringContents(id self, SEL _cmd, NSString *path, NSStringEncoding enc, NSError **err) {
    NSString *s = gOrigStringContents ? gOrigStringContents(self, _cmd, path, enc, err) : nil;
    if (CGMIsTargetPath(path) && s.length) {
        return [s stringByAppendingFormat:@"%@%@", kCGMInjectMark, gJSPayload ?: @""];
    }
    return s;
}

static void CGMInstallObjCHooks(void) {
    Method m1 = class_getClassMethod([NSData class], @selector(dataWithContentsOfFile:));
    if (m1) { gOrigDataWithContentsOfFile = (void *)method_getImplementation(m1); method_setImplementation(m1, (IMP)CGMDataWithContentsOfFile); }

    Method m2 = class_getClassMethod([NSData class], @selector(dataWithContentsOfFile:options:error:));
    if (m2) { gOrigDataWithContentsOfFileOpts = (void *)method_getImplementation(m2); method_setImplementation(m2, (IMP)CGMDataWithContentsOfFileOpts); }

    Method m3 = class_getInstanceMethod([NSData class], @selector(initWithContentsOfFile:));
    if (m3) { gOrigInitWithContentsOfFile = (void *)method_getImplementation(m3); method_setImplementation(m3, (IMP)CGMInitWithContentsOfFile); }

    Method m4 = class_getInstanceMethod([NSFileManager class], @selector(contentsAtPath:));
    if (m4) { gOrigContentsAtPath = (void *)method_getImplementation(m4); method_setImplementation(m4, (IMP)CGMContentsAtPath); }

    Method m5 = class_getClassMethod([NSString class], @selector(stringWithContentsOfFile:encoding:error:));
    if (m5) { gOrigStringContents = (void *)method_getImplementation(m5); method_setImplementation(m5, (IMP)CGMStringContents); }

    CGMLog(@"ObjC hooks installed (NSData x3, NSFileManager x1, NSString x1)");
}/* --- POSIX level hooks (installed only when MSHookFunction is reachable) --- */

typedef void *(*MSHookFunctionPtr)(void *symbol, void *replace, void **result);
static MSHookFunctionPtr gMSHookFunction = NULL;

typedef FILE *(*fopen_t)(const char *, const char *);
static fopen_t gOrigFopen = NULL;
static FILE *CGMfopen(const char *path, const char *mode) {
    if (CGMIsTargetPathC(path)) {
        NSString *tmp = CGMTempScriptPath();
        if (tmp) { return gOrigFopen(tmp.fileSystemRepresentation, mode); }
    }
    return gOrigFopen ? gOrigFopen(path, mode) : NULL;
}

typedef int (*open_t)(const char *, int, ...);
static open_t gOrigOpen = NULL;
static int CGMopen(const char *path, int oflag, mode_t mode) {
    if (CGMIsTargetPathC(path)) {
        NSString *tmp = CGMTempScriptPath();
        if (tmp) { return gOrigOpen(tmp.fileSystemRepresentation, oflag, mode); }
    }
    return gOrigOpen ? gOrigOpen(path, oflag, mode) : -1;
}

typedef int (*openat_t)(int, const char *, int, ...);
static openat_t gOrigOpenat = NULL;
static int CGMopenat(int fd, const char *path, int oflag, mode_t mode) {
    if (CGMIsTargetPathC(path)) {
        NSString *tmp = CGMTempScriptPath();
        if (tmp) { return gOrigOpenat(fd, tmp.fileSystemRepresentation, oflag, mode); }
    }
    return gOrigOpenat ? gOrigOpenat(fd, path, oflag, mode) : -1;
}

typedef int (*guarded_open_np_t)(const char *, const void *, uint32_t, int, ...);
static guarded_open_np_t gOrigGuardedOpen = NULL;
static int CGMguardedOpen(const char *path, const void *guard, uint32_t guardflags, int oflag, mode_t mode) {
    if (CGMIsTargetPathC(path)) {
        NSString *tmp = CGMTempScriptPath();
        if (tmp) { return gOrigGuardedOpen(tmp.fileSystemRepresentation, guard, guardflags, oflag, mode); }
    }
    return gOrigGuardedOpen ? gOrigGuardedOpen(path, guard, guardflags, oflag, mode) : -1;
}

typedef int (*open_dprotected_np_t)(const char *, int, int, int, ...);
static open_dprotected_np_t gOrigOpenDprotected = NULL;
static int CGMopenDprotected(const char *path, int oflag, int dpclass, int flags, mode_t mode) {
    if (CGMIsTargetPathC(path)) {
        NSString *tmp = CGMTempScriptPath();
        if (tmp) { return gOrigOpenDprotected(tmp.fileSystemRepresentation, oflag, dpclass, flags, mode); }
    }
    return gOrigOpenDprotected ? gOrigOpenDprotected(path, oflag, dpclass, flags, mode) : -1;
}

static void CGMDlopenTweakLibs(void) {
    const char *paths[] = {
        "/var/jb/usr/lib/libsubstrate.dylib",
        "/var/jb/usr/lib/libellekit.dylib",
        "/var/jb/usr/lib/libhooker.dylib",
        "/usr/lib/libsubstrate.dylib",
        NULL
    };
    for (int i = 0; paths[i]; i++) {
        void *h = dlopen(paths[i], RTLD_NOW | RTLD_GLOBAL);
        if (h) { CGMLog(@"dlopen ok %s", paths[i]); return; }
    }
}

static void CGMInstallPOSIXHooks(void) {
    gMSHookFunction = (MSHookFunctionPtr)dlsym(RTLD_DEFAULT, "MSHookFunction");
    if (!gMSHookFunction) {
        CGMDlopenTweakLibs();
        gMSHookFunction = (MSHookFunctionPtr)dlsym(RTLD_DEFAULT, "MSHookFunction");
    }
    if (!gMSHookFunction) { CGMLog(@"MSHookFunction unavailable -> POSIX hooks skipped"); return; }

    void *s1 = dlsym(RTLD_DEFAULT, "fopen");
    if (s1) { gMSHookFunction(s1, (void *)CGMfopen, (void **)&gOrigFopen); }
    void *s2 = dlsym(RTLD_DEFAULT, "fopen$DARWIN_EXTSN");
    if (s2) { gMSHookFunction(s2, (void *)CGMfopen, (void **)&gOrigFopen); }
    void *s3 = dlsym(RTLD_DEFAULT, "open");
    if (s3) { gMSHookFunction(s3, (void *)CGMopen, (void **)&gOrigOpen); }
    void *s4 = dlsym(RTLD_DEFAULT, "openat");
    if (s4) { gMSHookFunction(s4, (void *)CGMopenat, (void **)&gOrigOpenat); }
    void *s5 = dlsym(RTLD_DEFAULT, "guarded_open_np");
    if (s5) { gMSHookFunction(s5, (void *)CGMguardedOpen, (void **)&gOrigGuardedOpen); }
    void *s6 = dlsym(RTLD_DEFAULT, "open_dprotected_np");
    if (s6) { gMSHookFunction(s6, (void *)CGMopenDprotected, (void **)&gOrigOpenDprotected); }

    CGMLog(@"POSIX hooks: fopen=%d/%d open=%d openat=%d guarded=%d dprotected=%d",
           s1 ? 1 : 0, s2 ? 1 : 0, s3 ? 1 : 0, s4 ? 1 : 0, s5 ? 1 : 0, s6 ? 1 : 0);
}

/* ============================== bridge ==================================== */

static NSInteger gPendingSeq = 0;
static NSInteger gLastSeq = 0;
static NSDictionary *gEngineState = nil;
static BOOL gEngineReady = NO;
static NSString *gChosenMailbox = nil;

static NSString *CGMResolveActiveMailbox(void) {
    NSFileManager *fm = [NSFileManager defaultManager];
    NSMutableArray<NSString *> *cands = [NSMutableArray array];
    if (gMailboxPath) { [cands addObject:gMailboxPath]; }
    NSString *home = NSHomeDirectory();
    NSArray<NSString *> *roots = @[ home,
                                    [home stringByAppendingPathComponent:@"Documents"],
                                    [home stringByAppendingPathComponent:@"Library"],
                                    [home stringByAppendingPathComponent:@"tmp"] ];
    for (NSString *r in roots) {
        NSString *d = [r stringByAppendingPathComponent:kCGMMailboxName];
        if (![cands containsObject:d]) { [cands addObject:d]; }
    }
    for (NSString *d in cands) {
        if ([fm fileExistsAtPath:[d stringByAppendingPathComponent:@"js_hello.json"]] ||
            [fm fileExistsAtPath:[d stringByAppendingPathComponent:@"state.json"]]) {
            return d;
        }
    }
    return gMailboxPath;
}

static void CGMSendCommand(NSString *res, NSString *action, long long value) {
    if (!gChosenMailbox) { gChosenMailbox = CGMResolveActiveMailbox(); }
    if (!gChosenMailbox) { CGMLog(@"bridge not ready: no mailbox"); return; }
    gPendingSeq++;
    NSDictionary *cmd = @{
        @"seq": @(gPendingSeq),
        @"res": res,
        @"action": action,
        @"value": @(value),
        @"ts": @((long long)[[NSDate date] timeIntervalSince1970])
    };
    if (!CGMWriteJSON(cmd, [gChosenMailbox stringByAppendingPathComponent:@"cmd.json"])) {
        CGMLog(@"command write failed");
        return;
    }
    CGMLog(@"cmd#%ld -> %@ %@ %lld (waiting for JS receipt)", (long)gPendingSeq, res, action, value);
}

static void CGMRequestProbe(void) {
    if (!gChosenMailbox) { gChosenMailbox = CGMResolveActiveMailbox(); }
    if (!gChosenMailbox) { return; }
    static NSInteger probeSeq = 0;
    probeSeq++;
    CGMWriteJSON(@{ @"seq": @(probeSeq), @"ts": @((long long)[[NSDate date] timeIntervalSince1970]) },
                 [gChosenMailbox stringByAppendingPathComponent:@"probe_cmd.json"]);
}/* ============================== UI ======================================== */

static NSString * const kCGMResKeys[]  = { @"gem", @"coin", @"power", @"adcoupon" };
static NSString * const kCGMResNames[] = { @"钻石", @"金币", @"燃油", @"免广告券" };
static const int kCGMResCount = 4;

@interface CGMWindow : UIWindow
@end

@implementation CGMWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *v = [super hitTest:point withEvent:event];
    if (v == self || v == self.rootViewController.view) { return nil; }
    return v;
}
@end

@interface CGMViewController : UIViewController <UITextFieldDelegate>
@property (nonatomic, strong) UIButton *ball;
@property (nonatomic, strong) UIView *panel;
@property (nonatomic, strong) UIView *header;
@property (nonatomic, strong) UIButton *closeButton;
@property (nonatomic, strong) UISegmentedControl *resSeg;
@property (nonatomic, strong) UILabel *currentLabel;
@property (nonatomic, strong) UILabel *statusLabel;
@property (nonatomic, strong) UITextField *input;
@property (nonatomic, strong) UIButton *addButton;
@property (nonatomic, strong) UIButton *setButton;
@property (nonatomic, strong) UIButton *probeButton;
@property (nonatomic, strong) UITextView *logView;
@property (nonatomic, assign) BOOL panelVisible;
@property (nonatomic, assign) CGPoint ballCenter;
@property (nonatomic, assign) CGPoint panelCenter;
@property (nonatomic, assign) CGFloat keyboardShift;
@property (nonatomic, assign) BOOL didInitPositions;
@end

@implementation CGMViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor clearColor];
    self.view.userInteractionEnabled = YES;
    [self buildBall];
    [self buildPanel];
    self.panelVisible = NO;
    self.panel.hidden = YES;

    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChanged:)
                                                 name:UIKeyboardWillChangeFrameNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChanged:)
                                                 name:UIKeyboardWillHideNotification object:nil];

    __weak typeof(self) weakSelf = self;
    gLogSink = ^(NSString *line) { [weakSelf appendLog:line]; };
    if (gLogStore.count) { for (NSString *l in [gLogStore copy]) { [self appendLog:l]; } }
}

- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    gLogSink = nil;
}

- (void)buildBall {
    CGFloat s = 54.0;
    self.ball = [UIButton buttonWithType:UIButtonTypeCustom];
    self.ball.frame = CGRectMake(0, 0, s, s);
    self.ball.backgroundColor = [UIColor colorWithRed:0.10 green:0.55 blue:0.30 alpha:0.92];
    self.ball.layer.cornerRadius = s / 2.0;
    self.ball.layer.borderWidth = 1.0;
    self.ball.layer.borderColor = [UIColor colorWithWhite:1.0 alpha:0.65].CGColor;
    self.ball.titleLabel.font = [UIFont boldSystemFontOfSize:15.0];
    [self.ball setTitle:@"CG" forState:UIControlStateNormal];
    [self.ball addTarget:self action:@selector(togglePanel) forControlEvents:UIControlEventTouchUpInside];
    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(dragBall:)];
    [self.ball addGestureRecognizer:pan];
    [self.view addSubview:self.ball];
}

- (UILabel *)makeLabel:(NSString *)text size:(CGFloat)size bold:(BOOL)bold color:(UIColor *)color {
    UILabel *l = [[UILabel alloc] init];
    l.text = text;
    l.font = bold ? [UIFont boldSystemFontOfSize:size] : [UIFont systemFontOfSize:size];
    l.textColor = color;
    l.backgroundColor = [UIColor clearColor];
    return l;
}

- (UIButton *)makeButton:(NSString *)title color:(UIColor *)color action:(SEL)action {
    UIButton *b = [UIButton buttonWithType:UIButtonTypeCustom];
    [b setTitle:title forState:UIControlStateNormal];
    [b setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    b.titleLabel.font = [UIFont boldSystemFontOfSize:18.0];
    b.backgroundColor = color;
    b.layer.cornerRadius = 8.0;
    [b addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    return b;
}

- (void)buildPanel {
    self.panel = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 340, 430)];
    self.panel.backgroundColor = [UIColor colorWithWhite:0.08 alpha:0.94];
    self.panel.layer.cornerRadius = 14.0;
    self.panel.layer.borderWidth = 1.0;
    self.panel.layer.borderColor = [UIColor colorWithWhite:1.0 alpha:0.25].CGColor;
    self.panel.clipsToBounds = YES;

    self.header = [[UIView alloc] initWithFrame:CGRectZero];
    self.header.backgroundColor = [UIColor colorWithWhite:0.16 alpha:1.0];
    [self.panel addSubview:self.header];
    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(dragPanel:)];
    [self.header addGestureRecognizer:pan];

    UILabel *title = [self makeLabel:[NSString stringWithFormat:@"CookingGo 资源修改 v%@", CGM_VERSION]
                                size:13.0 bold:YES color:[UIColor whiteColor]];
    title.tag = 1001;
    [self.header addSubview:title];

    self.closeButton = [self makeButton:@"×" color:[UIColor colorWithWhite:0.35 alpha:1.0] action:@selector(togglePanel)];
    self.closeButton.titleLabel.font = [UIFont boldSystemFontOfSize:16.0];
    [self.header addSubview:self.closeButton];

    self.resSeg = [[UISegmentedControl alloc] initWithItems:@[kCGMResNames[0], kCGMResNames[1], kCGMResNames[2], kCGMResNames[3]]];
    self.resSeg.selectedSegmentIndex = 0;
    if (@available(iOS 13.0, *)) {
        self.resSeg.selectedSegmentTintColor = [UIColor colorWithRed:0.10 green:0.50 blue:0.85 alpha:1.0];
    }
    [self.resSeg addTarget:self action:@selector(resourceChanged) forControlEvents:UIControlEventValueChanged];
    [self.panel addSubview:self.resSeg];

    self.currentLabel = [self makeLabel:@"当前: --" size:15.0 bold:YES
                                 color:[UIColor colorWithRed:0.55 green:0.95 blue:0.65 alpha:1.0]];
    [self.panel addSubview:self.currentLabel];

    self.input = [[UITextField alloc] initWithFrame:CGRectZero];
    self.input.borderStyle = UITextBorderStyleRoundedRect;
    self.input.keyboardType = UIKeyboardTypeNumberPad;
    self.input.textAlignment = NSTextAlignmentCenter;
    self.input.font = [UIFont boldSystemFontOfSize:17.0];
    self.input.placeholder = @"输入数字，例如 100";
    self.input.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.95];
    self.input.textColor = [UIColor blackColor];
    self.input.delegate = self;
    [self.panel addSubview:self.input];

    UIToolbar *kbBar = [[UIToolbar alloc] initWithFrame:CGRectMake(0, 0, 320, 44)];
    UIBarButtonItem *spacer = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace target:nil action:nil];
    UIBarButtonItem *done = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(dismissKeyboard)];
    kbBar.items = @[spacer, done];
    [kbBar sizeToFit];
    self.input.inputAccessoryView = kbBar;

    self.addButton = [self makeButton:@"+" color:[UIColor colorWithRed:0.13 green:0.68 blue:0.32 alpha:1.0] action:@selector(addTapped)];
    self.setButton = [self makeButton:@"=" color:[UIColor colorWithRed:0.12 green:0.45 blue:0.90 alpha:1.0] action:@selector(setTapped)];
    [self.panel addSubview:self.addButton];
    [self.panel addSubview:self.setButton];

    self.probeButton = [self makeButton:@"自检" color:[UIColor colorWithWhite:0.35 alpha:1.0] action:@selector(probeTapped)];
    self.probeButton.titleLabel.font = [UIFont boldSystemFontOfSize:13.0];
    [self.panel addSubview:self.probeButton];

    self.statusLabel = [self makeLabel:@"JS: 等待注入..." size:11.0 bold:NO color:[UIColor colorWithWhite:0.85 alpha:1.0]];
    [self.panel addSubview:self.statusLabel];

    self.logView = [[UITextView alloc] initWithFrame:CGRectZero];
    self.logView.backgroundColor = [UIColor colorWithWhite:0.02 alpha:0.85];
    self.logView.textColor = [UIColor colorWithRed:0.75 green:0.95 blue:0.80 alpha:1.0];
    self.logView.font = [UIFont fontWithName:@"Menlo" size:10.0] ?: [UIFont systemFontOfSize:10.0];
    self.logView.editable = NO;
    self.logView.scrollEnabled = YES;
    self.logView.layer.cornerRadius = 6.0;
    [self.panel addSubview:self.logView];

    [self.view addSubview:self.panel];
}- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    [self layoutChrome];
}

- (CGRect)safeFrame {
    CGRect b = self.view.bounds;
    if (@available(iOS 11.0, *)) {
        UIEdgeInsets in = self.view.safeAreaInsets;
        b.origin.x += in.left; b.origin.y += in.top;
        b.size.width -= (in.left + in.right);
        b.size.height -= (in.top + in.bottom);
    }
    return b;
}

- (void)layoutChrome {
    CGRect safe = [self safeFrame];
    if (safe.size.width < 10 || safe.size.height < 10) { return; }

    if (!self.didInitPositions) {
        self.didInitPositions = YES;
        self.ballCenter = CGPointMake(CGRectGetMaxX(safe) - 40.0, CGRectGetMidY(safe) - 40.0);
        self.panelCenter = CGPointMake(CGRectGetMidX(safe), CGRectGetMidY(safe));
    }

    CGFloat panelW = MIN(340.0, safe.size.width - 16.0);
    CGFloat panelH = MIN(430.0, safe.size.height - 16.0);
    CGFloat headerH = 34.0;
    CGFloat pad = 10.0;
    CGFloat inputH = 40.0;
    CGFloat btnW = 56.0;

    CGRect pf = self.panel.frame;
    pf.size = CGSizeMake(panelW, panelH);
    self.panel.frame = pf;
    self.panel.center = CGPointMake(self.panelCenter.x + self.keyboardShift, self.panelCenter.y);

    self.ball.center = self.ballCenter;

    self.header.frame = CGRectMake(0, 0, panelW, headerH);
    UILabel *title = [self.header viewWithTag:1001];
    title.frame = CGRectMake(pad, 0, panelW - headerH - 2 * pad, headerH);
    self.closeButton.frame = CGRectMake(panelW - headerH, 0, headerH, headerH);

    CGFloat y = headerH + pad;
    self.resSeg.frame = CGRectMake(pad, y, panelW - 2 * pad, 32.0);
    y += 32.0 + 8.0;
    self.currentLabel.frame = CGRectMake(pad, y, panelW - 2 * pad, 20.0);
    y += 20.0 + 6.0;

    self.input.frame = CGRectMake(pad, y, panelW - 2 * pad - (btnW * 2.0 + 12.0), inputH);
    self.addButton.frame = CGRectMake(CGRectGetMaxX(self.input.frame) + 6.0, y, btnW, inputH);
    self.setButton.frame = CGRectMake(CGRectGetMaxX(self.addButton.frame) + 6.0, y, btnW, inputH);
    y += inputH + 8.0;

    self.probeButton.frame = CGRectMake(pad, y, 60.0, 24.0);
    self.statusLabel.frame = CGRectMake(pad + 68.0, y, panelW - 3.0 * pad - 68.0, 24.0);
    y += 24.0 + 8.0;

    CGFloat logH = panelH - y - pad;
    if (logH < 60.0) { logH = 60.0; }
    self.logView.frame = CGRectMake(pad, y, panelW - 2.0 * pad, logH);
}

- (void)refreshStatus {
    if (!gChosenMailbox) { gChosenMailbox = CGMResolveActiveMailbox(); }
    NSString *jsState = gEngineReady ? @"引擎已就绪" : @"等待引擎...";
    self.statusLabel.text = gChosenMailbox
        ? [NSString stringWithFormat:@"JS: %@", jsState]
        : [NSString stringWithFormat:@"JS: %@ 桥未建立", jsState];

    NSInteger seg = self.resSeg.selectedSegmentIndex;
    if (seg < 0 || seg >= kCGMResCount) { seg = 0; }
    NSString *key = kCGMResKeys[seg];
    id v = gEngineState[key];
    if ([v isKindOfClass:[NSNumber class]]) {
        self.currentLabel.text = [NSString stringWithFormat:@"%@ 当前: %@", kCGMResNames[seg], v];
    } else {
        self.currentLabel.text = [NSString stringWithFormat:@"%@ 当前: --", kCGMResNames[seg]];
    }
}

- (void)resourceChanged { [self refreshStatus]; }
- (void)dismissKeyboard { [self.input resignFirstResponder]; }

- (void)togglePanel {
    self.panelVisible = !self.panelVisible;
    self.panel.hidden = !self.panelVisible;
    if (self.panelVisible) { [self refreshStatus]; } else { [self dismissKeyboard]; }
}

- (void)dragBall:(UIPanGestureRecognizer *)g {
    CGPoint t = [g translationInView:self.view];
    CGPoint c = self.ball.center;
    c.x += t.x; c.y += t.y;
    [g setTranslation:CGPointZero inView:self.view];
    CGRect safe = [self safeFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    c.x = MAX(CGRectGetMinX(safe) + r, MIN(CGRectGetMaxX(safe) - r, c.x));
    c.y = MAX(CGRectGetMinY(safe) + r, MIN(CGRectGetMaxY(safe) - r, c.y));
    self.ball.center = c;
    self.ballCenter = c;
}

- (void)dragPanel:(UIPanGestureRecognizer *)g {
    CGPoint t = [g translationInView:self.view];
    CGPoint c = self.panel.center;
    c.x += t.x; c.y += t.y;
    [g setTranslation:CGPointZero inView:self.view];
    CGRect safe = [self safeFrame];
    CGFloat hw = self.panel.bounds.size.width / 2.0;
    CGFloat hh = self.panel.bounds.size.height / 2.0;
    c.x = MAX(CGRectGetMinX(safe) + hw, MIN(CGRectGetMaxX(safe) - hw, c.x));
    c.y = MAX(CGRectGetMinY(safe) + hh, MIN(CGRectGetMaxY(safe) - hh, c.y));
    self.panel.center = c;
    self.panelCenter = c;
}

- (void)appendLog:(NSString *)line {
    if (![NSThread isMainThread]) {
        NSString *copy = [line copy];
        dispatch_async(dispatch_get_main_queue(), ^{ [self appendLog:copy]; });
        return;
    }
    NSString *old = self.logView.text ?: @"";
    NSString *next = [old stringByAppendingFormat:@"%@\n", line];
    if (next.length > 12000) { next = [next substringFromIndex:next.length - 9000]; }
    self.logView.text = next;
    if (next.length > 0) { [self.logView scrollRangeToVisible:NSMakeRange(next.length - 1, 1)]; }
}

- (long long)inputValueOrZero:(BOOL *)ok {
    NSString *s = [self.input.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    s = [s stringByReplacingOccurrencesOfString:@"+" withString:@""];
    s = [s stringByReplacingOccurrencesOfString:@"=" withString:@""];
    if (s.length == 0) { *ok = NO; return 0; }
    NSCharacterSet *bad = [[NSCharacterSet decimalDigitCharacterSet] invertedSet];
    if ([s rangeOfCharacterFromSet:bad].location != NSNotFound) { *ok = NO; return 0; }
    double d = [s doubleValue];
    if (d < 0) { d = 0; }
    if (d > 2000000000.0) { d = 2000000000.0; }
    *ok = YES;
    return (long long)d;
}

- (void)runAction:(NSString *)action {
    BOOL ok = NO;
    long long v = [self inputValueOrZero:&ok];
    if (!ok) {
        [self appendLog:@"× 输入无效：只填数字，例如 100（不要写 + 或 =）"];
        return;
    }
    NSInteger seg = self.resSeg.selectedSegmentIndex;
    if (seg < 0 || seg >= kCGMResCount) { seg = 0; }
    NSString *key = kCGMResKeys[seg];
    NSString *name = kCGMResNames[seg];

    id before = gEngineState[key];
    NSString *beforeStr = [before isKindOfClass:[NSNumber class]] ? [NSString stringWithFormat:@"%@", before] : @"?";
    NSString *expr = [action isEqualToString:@"add"]
        ? [NSString stringWithFormat:@"%@ + %lld", beforeStr, v]
        : [NSString stringWithFormat:@"%@ = %lld", beforeStr, v];

    [self appendLog:@"-----------------------------"];
    [self appendLog:[NSString stringWithFormat:@"资源: %@", name]];
    [self appendLog:[NSString stringWithFormat:@"修改前: %@", beforeStr]];
    [self appendLog:[NSString stringWithFormat:@"输入表达: %@", expr]];
    [self appendLog:@"修改后: 等待 JS 回执..."];
    [self dismissKeyboard];
    CGMSendCommand(key, action, v);
}

- (void)addTapped { [self runAction:@"add"]; }
- (void)setTapped { [self runAction:@"set"]; }

- (void)probeTapped {
    [self appendLog:@"→ 触发 JS 运行时自检 (probe.json)"];
    CGMRequestProbe();
}

- (void)keyboardChanged:(NSNotification *)n {
    if ([n.name isEqualToString:UIKeyboardWillHideNotification]) {
        self.keyboardShift = 0;
        [UIView animateWithDuration:0.2 animations:^{ [self layoutChrome]; }];
        return;
    }
    NSDictionary *info = n.userInfo;
    CGRect end = [info[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    CGRect kb = [self.view convertRect:end fromView:nil];
    if (kb.size.height <= 0) { return; }
    CGRect panel = self.panel.frame;
    CGFloat overlap = CGRectGetMaxY(panel) - CGRectGetMinY(kb) + 12.0;
    if (overlap > 0) { self.keyboardShift -= overlap; }
    if (self.keyboardShift < -(CGRectGetMidY([self safeFrame]))) { self.keyboardShift = -(CGRectGetMidY([self safeFrame])); }
    double dv = [info[UIKeyboardAnimationDurationUserInfoKey] doubleValue];
    [UIView animateWithDuration:(dv > 0 ? dv : 0.25) animations:^{ [self layoutChrome]; }];
}

- (BOOL)textFieldShouldReturn:(UITextField *)tf { [tf resignFirstResponder]; return YES; }
@end/* ============================== controller ================================ */

static CGMWindow *gWindow = nil;
static CGMViewController *gVC = nil;
static NSTimer *gTimer = nil;
static NSInteger gLastProbeTs = -1;

static UIWindowScene *CGMFindScene(void) {
    for (UIScene *s in [UIApplication sharedApplication].connectedScenes) {
        if (![s isKindOfClass:[UIWindowScene class]]) { continue; }
        if (s.activationState == UISceneActivationStateForegroundActive) { return (UIWindowScene *)s; }
    }
    for (UIScene *s in [UIApplication sharedApplication].connectedScenes) {
        if ([s isKindOfClass:[UIWindowScene class]]) { return (UIWindowScene *)s; }
    }
    return nil;
}

static void CGMSetupWindow(void);

static void CGMSetupWindowRetry(void) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ CGMSetupWindow(); });
}

static void CGMSetupWindow(void) {
    if (gWindow) { return; }
    if (![NSThread isMainThread]) { dispatch_async(dispatch_get_main_queue(), ^{ CGMSetupWindow(); }); return; }
    UIWindowScene *scene = CGMFindScene();
    if (!scene) { CGMSetupWindowRetry(); return; }
    @try {
        gVC = [[CGMViewController alloc] init];
        gWindow = [[CGMWindow alloc] initWithWindowScene:scene];
        gWindow.frame = scene.coordinateSpace.bounds;
        gWindow.rootViewController = gVC;
        gWindow.windowLevel = UIWindowLevelAlert + 100.0;
        gWindow.backgroundColor = [UIColor clearColor];
        gWindow.opaque = NO;
        gWindow.hidden = NO;
        CGMLog(@"overlay window created (level=%.0f)", (double)gWindow.windowLevel);
    } @catch (NSException *e) {
        CGMLog(@"overlay window failed: %@", e.reason);
        gWindow = nil;
        CGMSetupWindowRetry();
    }
}

static void CGMTick(void) {
    @try {
        if (!gChosenMailbox) { gChosenMailbox = CGMResolveActiveMailbox(); }
        if (!gChosenMailbox) { [gVC refreshStatus]; return; }

        NSDictionary *hello = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"js_hello.json"]);
        NSDictionary *state = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"state.json"]);
        if (state) {
            gEngineState = state;
            id ready = state[@"ready"];
            gEngineReady = [ready isKindOfClass:[NSNumber class]] ? [ready boolValue] : NO;
        }

        NSDictionary *res = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"res.json"]);
        if (res) {
            NSInteger seq = [res[@"seq"] integerValue];
            if (seq != gLastSeq) {
                gLastSeq = seq;
                BOOL ok = [res[@"ok"] boolValue];
                NSString *key = res[@"res"] ?: @"?";
                if (ok) {
                    [gVC appendLog:[NSString stringWithFormat:@"← JS 回执 #%ld", (long)seq]];
                    [gVC appendLog:[NSString stringWithFormat:@"  修改前: %@", res[@"before"] ?: @"?"]];
                    [gVC appendLog:[NSString stringWithFormat:@"  输入表达: %@", res[@"expr"] ?: @""]];
                    [gVC appendLog:[NSString stringWithFormat:@"  修改后: %@", res[@"after"] ?: @"?"]];
                    id after = res[@"after"];
                    id stv = gEngineState[key];
                    if ([stv isKindOfClass:[NSNumber class]] && [after isKindOfClass:[NSNumber class]]) {
                        [gVC appendLog:([stv longLongValue] == [after longLongValue])
                            ? @"  复核: state.json 一致 ✔"
                            : @"  复核: state.json 不一致 ✘"];
                    }
                } else {
                    [gVC appendLog:[NSString stringWithFormat:@"← JS 回执 #%ld 失败: %@",
                                    (long)seq, res[@"error"] ?: @"unknown"]];
                }
            }
        }

        NSDictionary *probe = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"probe.json"]);
        if (probe) {
            NSInteger pv = [probe[@"ts"] integerValue];
            if (pv != gLastProbeTs) {
                gLastProbeTs = pv;
                [gVC appendLog:[NSString stringWithFormat:@"[自检] require=%@ jsb=%@ cc=%@",
                                probe[@"typeofRequire"] ?: @"?", probe[@"typeofJsb"] ?: @"?", probe[@"typeofCc"] ?: @"?"]];
                if (probe[@"gameDefault"]) {
                    [gVC appendLog:[NSString stringWithFormat:@"[自检] Game.default=%@ managers=%@",
                                    probe[@"gameDefault"], probe[@"managers"] ? @( [probe[@"managers"] count] ) : @"?"]];
                }
                if (probe[@"eventIdCount"]) {
                    [gVC appendLog:[NSString stringWithFormat:@"[自检] EVENT_ID=%@ coreEvent=%@ playerInfo字段=%@",
                                    probe[@"eventIdCount"], probe[@"coreEvent"] ?: @"?", probe[@"playerInfoKeys"] ?: @"?"]];
                }
                if (probe[@"state"]) {
                    [gVC appendLog:[NSString stringWithFormat:@"[自检] state=%@", probe[@"state"]]];
                }
            }
        }

        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }
        [gVC refreshStatus];
    } @catch (NSException *e) {
        CGMLog(@"tick exception: %@", e.reason);
    }
}

static void CGMStart(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        CGMSetupWindow();
        if (!gTimer) {
            gTimer = [NSTimer timerWithTimeInterval:0.4 repeats:YES block:^(NSTimer *t) { CGMTick(); }];
            [[NSRunLoop mainRunLoop] addTimer:gTimer forMode:NSRunLoopCommonModes];
        }
    });
}

/* ============================== entry ===================================== */

__attribute__((constructor))
static void CGMLoad(void) {
    @autoreleasepool {
        NSString *bid = [[NSBundle mainBundle] bundleIdentifier];
        if (![bid isEqualToString:kCGMTargetBundle]) {
            NSLog(@"[CookingGoMod] bundle %@ is not the target, skipping", bid);
            return;
        }
        @try {
            gJSPayload = [[NSString alloc] initWithBytes:kCGMBootstrapJS
                                                  length:strlen(kCGMBootstrapJS)
                                                encoding:NSUTF8StringEncoding];
        } @catch (NSException *e) { gJSPayload = nil; }
        if (!gJSPayload.length) {
            NSLog(@"[CookingGoMod] JS payload missing, aborting");
            return;
        }

        CGMEnsureMailbox();
        CGMLog(@"CookingGoMod v%@ loaded (bundle=%@)", CGM_VERSION, bid);
        CGMInstallObjCHooks();
        CGMInstallPOSIXHooks();
        CGMLog(@"target script: %@", CGMSourcePath() ?: @"<not found in bundle>");
        CGMStart();
    }
}
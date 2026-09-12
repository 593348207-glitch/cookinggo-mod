import io, re, sys

P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
orig = s

def cut(start_marker, end_marker, replacement, what):
    global s
    i = s.find(start_marker)
    assert i >= 0, "start marker not found: " + what
    j = s.find(end_marker, i)
    assert j > i, "end marker not found: " + what
    s = s[:i] + replacement + s[j:]
    print("replaced", what)

# ---------------------------------------------------------------- 1. stdarg
s = s.replace("#import <string.h>", "#import <string.h>\n#import <stdarg.h>", 1)

# ---------------------------------------------------------------- 2. POSIX block
posix_new = r'''/* --- POSIX level hooks (installed only when MSHookFunction is reachable) --- */

typedef void *(*MSHookFunctionPtr)(void *symbol, void *replace, void **result);
static MSHookFunctionPtr gMSHookFunction = NULL;

/* Redirect an open-family call on the target script to the pre-patched copy. */
static const char *CGMRedirectPath(const char *path) {
    if (!CGMIsTargetPathC(path)) { return path; }
    NSString *tmp = CGMTempScriptPath();
    if (!tmp) { return path; }
    return tmp.fileSystemRepresentation;
}

typedef FILE *(*fopen_t)(const char *, const char *);
static fopen_t gOrigFopen = NULL;
static FILE *CGMfopen(const char *path, const char *mode) {
    if (!gOrigFopen) { return NULL; }
    return gOrigFopen(CGMRedirectPath(path), mode);
}

static fopen_t gOrigFopenExtsn = NULL;
static FILE *CGMfopenExtsn(const char *path, const char *mode) {
    if (!gOrigFopenExtsn) { return NULL; }
    return gOrigFopenExtsn(CGMRedirectPath(path), mode);
}

typedef int (*open_t)(const char *, int, ...);
static open_t gOrigOpen = NULL;
static int CGMopen(const char *path, int oflag, ...) {
    if (!gOrigOpen) { return -1; }
    va_list ap; va_start(ap, oflag); mode_t m = (mode_t)va_arg(ap, int); va_end(ap);
    if (oflag & O_CREAT) { return gOrigOpen(CGMRedirectPath(path), oflag, m); }
    return gOrigOpen(CGMRedirectPath(path), oflag);
}

typedef int (*openat_t)(int, const char *, int, ...);
static openat_t gOrigOpenat = NULL;
static int CGMopenat(int fd, const char *path, int oflag, ...) {
    if (!gOrigOpenat) { return -1; }
    va_list ap; va_start(ap, oflag); mode_t m = (mode_t)va_arg(ap, int); va_end(ap);
    if ((oflag & O_CREAT) && fd == AT_FDCWD) { return gOrigOpenat(fd, CGMRedirectPath(path), oflag, m); }
    return gOrigOpenat(fd, path, oflag, m);
}

typedef int (*guarded_open_np_t)(const char *, const void *, uint32_t, int, ...);
static guarded_open_np_t gOrigGuardedOpen = NULL;
static int CGMguardedOpen(const char *path, const void *guard, uint32_t guardflags, int oflag, ...) {
    if (!gOrigGuardedOpen) { return -1; }
    va_list ap; va_start(ap, oflag); mode_t m = (mode_t)va_arg(ap, int); va_end(ap);
    /* never redirect an open that carries a guard: the guard is bound to the inode */
    (void)m;
    return gOrigGuardedOpen(path, guard, guardflags, oflag, m);
}

typedef int (*open_dprotected_np_t)(const char *, int, int, int, ...);
static open_dprotected_np_t gOrigOpenDprotected = NULL;
static int CGMopenDprotected(const char *path, int oflag, int dpclass, int flags, ...) {
    if (!gOrigOpenDprotected) { return -1; }
    va_list ap; va_start(ap, flags); mode_t m = (mode_t)va_arg(ap, int); va_end(ap);
    if (oflag & O_CREAT) { return gOrigOpenDprotected(CGMRedirectPath(path), oflag, dpclass, flags, m); }
    return gOrigOpenDprotected(path, oflag, dpclass, flags, m);
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
    if (!gCfgPosix) { CGMLog(@"POSIX hooks disabled by config"); return; }

    gMSHookFunction = (MSHookFunctionPtr)dlsym(RTLD_DEFAULT, "MSHookFunction");
    if (!gMSHookFunction) {
        CGMDlopenTweakLibs();
        gMSHookFunction = (MSHookFunctionPtr)dlsym(RTLD_DEFAULT, "MSHookFunction");
    }
    if (!gMSHookFunction) { CGMLog(@"MSHookFunction unavailable -> POSIX hooks skipped"); return; }

    void *s1 = dlsym(RTLD_DEFAULT, "fopen");
    if (s1) { gMSHookFunction(s1, (void *)CGMfopen, (void **)&gOrigFopen); }
    void *s2 = dlsym(RTLD_DEFAULT, "fopen$DARWIN_EXTSN");
    if (s2) { gMSHookFunction(s2, (void *)CGMfopenExtsn, (void **)&gOrigFopenExtsn); }
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

'''
cut("/* --- POSIX level hooks", "/* ============================== bridge", posix_new, "POSIX block")

# ---------------------------------------------------------------- 3. config block
config_block = r'''/* ============================== configuration ============================= */

static int gCfgObjc    = 1;   /* ObjC file-API hooks: the JS injection path      */
static int gCfgPosix   = 0;   /* POSIX open-family hooks: invasive, opt-in       */
static int gCfgOverlay = 1;   /* floating panel UI                               */

static void CGMApplyConfigLine(const char *line) {
    if (!line) { return; }
    while (*line == ' ' || *line == '\t') { line++; }
    if (*line == '#' || *line == '\0' || *line == '\n' || *line == '\r') { return; }
    const char *eq = strchr(line, '=');
    if (!eq) { return; }
    char key[64];
    size_t n = (size_t)(eq - line);
    while (n > 0 && (line[n - 1] == ' ' || line[n - 1] == '\t')) { n--; }
    if (n >= sizeof(key)) { return; }
    memcpy(key, line, n);
    key[n] = '\0';
    int val = (eq[1] == '1') ? 1 : 0;
    if (strcmp(key, "objc") == 0) { gCfgObjc = val; }
    else if (strcmp(key, "posix") == 0) { gCfgPosix = val; }
    else if (strcmp(key, "overlay") == 0) { gCfgOverlay = val; }
}

static void CGMReadConfigFile(const char *path) {
    if (!path) { return; }
    FILE *f = fopen(path, "r");
    if (!f) { return; }
    char buf[512];
    while (fgets(buf, sizeof(buf), f)) { CGMApplyConfigLine(buf); }
    fclose(f);
}

/* Read before installing any hook, and before the mailbox is relied upon. */
static void CGMReadConfig(void) {
    CGMReadConfigFile("/var/jb/usr/lib/TweakInject/CookingGoMod.cfg");
    NSString *home = NSHomeDirectory();
    if (home.length) {
        NSString *p = [home stringByAppendingPathComponent:@"Documents/cookingmod/cfg.txt"];
        CGMReadConfigFile(p.fileSystemRepresentation);
    }
    CGMLog(@"config: objc=%d posix=%d overlay=%d", gCfgObjc, gCfgPosix, gCfgOverlay);
}

'''
cut("/* ============================== write helpers", "/* ============================== mailbox", config_block + "/* ============================== mailbox", "config block")

# ---------------------------------------------------------------- 4. start / overlay
start_new = r'''static void CGMStartTick(void) {
    if (gTimer) { return; }
    gTimer = [NSTimer timerWithTimeInterval:0.4 repeats:YES block:^(NSTimer *t) { CGMTick(); }];
    [[NSRunLoop mainRunLoop] addTimer:gTimer forMode:NSRunLoopCommonModes];
}

static BOOL gOverlayStarted = NO;

/* The overlay must not be created from the load-time constructor: doing that in
   1.0.1 killed the process before the engine ever loaded its scripts. */
static void CGMOnLaunchDone(void) {
    if (gOverlayStarted) { return; }
    gOverlayStarted = YES;
    if (!gCfgOverlay) {
        CGMLog(@"overlay disabled by config -> bridge only");
        CGMStartTick();
        return;
    }
    CGMLog(@"launch finished -> scheduling overlay");
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.8 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        CGMSetupWindow();
        CGMStartTick();
    });
}

static void CGMStart(void) {
    if ([NSThread isMainThread]) { CGMOnLaunchDone(); return; }
    dispatch_async(dispatch_get_main_queue(), ^{ CGMOnLaunchDone(); });
}

'''
cut("static void CGMStart(void) {", "/* ============================== entry", start_new, "CGMStart")

# ---------------------------------------------------------------- 5. entry
entry_new = r'''__attribute__((constructor))
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

        CGMReadConfig();
        CGMEnsureMailbox();
        CGMLog(@"CookingGoMod v%@ loaded (bundle=%@) payload=%lu bytes",
               CGM_VERSION, bid, (unsigned long)gJSPayload.length);
        if (gMailboxPath) {
            CGMWriteString(gJSPayload, [gMailboxPath stringByAppendingPathComponent:@"bootstrap.js"]);
        }
        if (gCfgObjc) { CGMInstallObjCHooks(); } else { CGMLog(@"ObjC hooks disabled by config"); }
        CGMInstallPOSIXHooks();
        CGMLog(@"target script: %@", CGMSourcePath() ?: @"<not found in bundle>");

        /* Primary trigger plus a fallback in case the notification was already
           posted before this constructor ran. */
        [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification
                                                          object:nil
                                                           queue:[NSOperationQueue mainQueue]
                                                      usingBlock:^(NSNotification *note) { CGMOnLaunchDone(); }];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(3.0 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{ CGMOnLaunchDone(); });
    }
}
'''
i = s.find("__attribute__((constructor))")
assert i > 0
s = s[:i] + entry_new
print("replaced entry")

assert s != orig
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("written", len(s), "bytes")
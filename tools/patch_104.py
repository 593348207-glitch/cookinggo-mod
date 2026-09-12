import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# ---- 1. hit counters -------------------------------------------------------
anchor = "/* ============================== JS injection ============================== */"
hits = r'''/* ============================== hit counters =============================== */

enum { kCGMHitDataClass = 0, kCGMHitDataClassOpts, kCGMHitDataInit, kCGMHitDataInitOpts,
       kCGMHitFmContents, kCGMHitStrClass, kCGMHitStrInit, kCGMHitStrInitUsed,
       kCGMHitFopen, kCGMHitOpen, kCGMHitOpenat, kCGMHitGuarded, kCGMHitDprotected,
       kCGMHitCount };
static const char *kCGMHitNames[kCGMHitCount] = {
    "NSData.dataWithContentsOfFile", "NSData.dataWithContentsOfFile:options:error:",
    "NSData.initWithContentsOfFile", "NSData.initWithContentsOfFile:options:error:",
    "NSFileManager.contentsAtPath", "NSString.stringWithContentsOfFile:encoding:error:",
    "NSString.initWithContentsOfFile:encoding:error:", "NSString.initWithContentsOfFile:usedEncoding:error:",
    "fopen", "open", "openat", "guarded_open_np", "open_dprotected_np"
};
static volatile int gHits[kCGMHitCount];
static void CGMBumpHit(int i) { if (i >= 0 && i < kCGMHitCount) { __sync_fetch_and_add(&gHits[i], 1); } }

''' + anchor
s = s.replace(anchor, hits, 1); n += 1
print("hits block:", n)

# ---- 2. note hooks ---------------------------------------------------------
for old, new in [
 ('    NSData *d = gOrigDataWithContentsOfFile ? gOrigDataWithContentsOfFile(self, _cmd, path) : nil;\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;',
  '    NSData *d = gOrigDataWithContentsOfFile ? gOrigDataWithContentsOfFile(self, _cmd, path) : nil;\n    CGMBumpHit(kCGMHitDataClass);\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;'),
 ('    NSData *d = gOrigDataWithContentsOfFileOpts ? gOrigDataWithContentsOfFileOpts(self, _cmd, path, opts, err) : nil;\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;',
  '    NSData *d = gOrigDataWithContentsOfFileOpts ? gOrigDataWithContentsOfFileOpts(self, _cmd, path, opts, err) : nil;\n    CGMBumpHit(kCGMHitDataClassOpts);\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;'),
 ('    id d = gOrigInitWithContentsOfFile ? gOrigInitWithContentsOfFile(self, _cmd, path) : nil;\n    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return d; }',
  '    id d = gOrigInitWithContentsOfFile ? gOrigInitWithContentsOfFile(self, _cmd, path) : nil;\n    CGMBumpHit(kCGMHitDataInit);\n    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return d; }'),
 ('    NSData *d = gOrigContentsAtPath ? gOrigContentsAtPath(self, _cmd, path) : nil;\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;',
  '    NSData *d = gOrigContentsAtPath ? gOrigContentsAtPath(self, _cmd, path) : nil;\n    CGMBumpHit(kCGMHitFmContents);\n    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }\n    CGMNoteJSReadOnce(path);\n    return d;'),
 ('    NSString *s = gOrigStringContents ? gOrigStringContents(self, _cmd, path, enc, err) : nil;\n    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return s; }',
  '    NSString *s = gOrigStringContents ? gOrigStringContents(self, _cmd, path, enc, err) : nil;\n    CGMBumpHit(kCGMHitStrClass);\n    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return s; }'),
]:
    assert old in s, "miss: " + old[:70]
    s = s.replace(old, new, 1); n += 1
print("note hooks:", n)

# ---- 3. new hook implementations ------------------------------------------
anchor2 = "static void CGMInstallObjCHooks(void) {"
newhooks = r'''/* NSString / NSData -initWithContentsOf... : the surface cocos2d-x
   FileUtilsApple::getStringFromFile actually uses for text assets. */
static id (*gOrigDataInitContentsOpts)(id, SEL, NSString *, NSDataReadingOptions, NSError **);
static id CGMDataInitContentsOpts(id self, SEL _cmd, NSString *path, NSDataReadingOptions opts, NSError **err) {
    id d = gOrigDataInitContentsOpts ? gOrigDataInitContentsOpts(self, _cmd, path, opts, err) : nil;
    CGMBumpHit(kCGMHitDataInitOpts);
    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return d; }
    if ([d isKindOfClass:[NSData class]]) {
        NSData *inj = CGMInjectedData(d, path);
        if (inj != d) { return (__bridge id)CFBridgingRetain(inj); }
    }
    return d;
}

static id (*gOrigStrInitContents)(id, SEL, NSString *, NSStringEncoding, NSError **);
static id CGMStrInitContents(id self, SEL _cmd, NSString *path, NSStringEncoding enc, NSError **err) {
    id r = gOrigStrInitContents ? gOrigStrInitContents(self, _cmd, path, enc, err) : nil;
    CGMBumpHit(kCGMHitStrInit);
    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return r; }
    if ([r isKindOfClass:[NSString class]] && gJSPayload.length) {
        NSString *merged = [r stringByAppendingFormat:@"%@%@", kCGMInjectMark, gJSPayload];
        if (!gInjectLogDone) {
            gInjectLogDone = YES;
            CGMLog(@"JS injected through NSString initWithContentsOfFile:encoding:error: (+%lu bytes)",
                   (unsigned long)gJSPayload.length);
        }
        return (__bridge id)CFBridgingRetain(merged);
    }
    return r;
}

static id (*gOrigStrInitContentsUsed)(id, SEL, NSString *, NSStringEncoding *, NSError **);
static id CGMStrInitContentsUsed(id self, SEL _cmd, NSString *path, NSStringEncoding *enc, NSError **err) {
    id r = gOrigStrInitContentsUsed ? gOrigStrInitContentsUsed(self, _cmd, path, enc, err) : nil;
    CGMBumpHit(kCGMHitStrInitUsed);
    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return r; }
    if ([r isKindOfClass:[NSString class]] && gJSPayload.length) {
        NSString *merged = [r stringByAppendingFormat:@"%@%@", kCGMInjectMark, gJSPayload];
        return (__bridge id)CFBridgingRetain(merged);
    }
    return r;
}

''' + anchor2
s = s.replace(anchor2, newhooks, 1); n += 1

# ---- 4. install the new hooks ---------------------------------------------
old_install = '''    Method m5 = class_getClassMethod([NSString class], @selector(stringWithContentsOfFile:encoding:error:));
    if (m5) { gOrigStringContents = (void *)method_getImplementation(m5); method_setImplementation(m5, (IMP)CGMStringContents); }

    CGMLog(@"ObjC hooks installed (NSData x3, NSFileManager x1, NSString x1)");'''
new_install = '''    Method m5 = class_getClassMethod([NSString class], @selector(stringWithContentsOfFile:encoding:error:));
    if (m5) { gOrigStringContents = (void *)method_getImplementation(m5); method_setImplementation(m5, (IMP)CGMStringContents); }

    Method m6 = class_getInstanceMethod([NSData class], @selector(initWithContentsOfFile:options:error:));
    if (m6) { gOrigDataInitContentsOpts = (void *)method_getImplementation(m6); method_setImplementation(m6, (IMP)CGMDataInitContentsOpts); }

    Method m7 = class_getInstanceMethod([NSString class], @selector(initWithContentsOfFile:encoding:error:));
    if (m7) { gOrigStrInitContents = (void *)method_getImplementation(m7); method_setImplementation(m7, (IMP)CGMStrInitContents); }

    Method m8 = class_getInstanceMethod([NSString class], @selector(initWithContentsOfFile:usedEncoding:error:));
    if (m8) { gOrigStrInitContentsUsed = (void *)method_getImplementation(m8); method_setImplementation(m8, (IMP)CGMStrInitContentsUsed); }

    CGMLog(@"ObjC hooks installed (NSData x4, NSFileManager x1, NSString x3) [m6=%d m7=%d m8=%d]",
           m6 ? 1 : 0, m7 ? 1 : 0, m8 ? 1 : 0);'''
assert old_install in s
s = s.replace(old_install, new_install, 1); n += 1
print("install block patched")

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("total patches:", n, "size:", len(s))
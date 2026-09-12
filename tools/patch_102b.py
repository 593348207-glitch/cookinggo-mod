import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

pairs = [
("""    NSData *d = gOrigDataWithContentsOfFileOpts ? gOrigDataWithContentsOfFileOpts(self, _cmd, path, opts, err) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    return d;""",
 """    NSData *d = gOrigDataWithContentsOfFileOpts ? gOrigDataWithContentsOfFileOpts(self, _cmd, path, opts, err) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    CGMNoteJSReadOnce(path);
    return d;"""),

("""    id d = gOrigInitWithContentsOfFile ? gOrigInitWithContentsOfFile(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path) && [d isKindOfClass:[NSData class]]) {""",
 """    id d = gOrigInitWithContentsOfFile ? gOrigInitWithContentsOfFile(self, _cmd, path) : nil;
    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return d; }
    if ([d isKindOfClass:[NSData class]]) {"""),

("""    NSData *d = gOrigContentsAtPath ? gOrigContentsAtPath(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    return d;""",
 """    NSData *d = gOrigContentsAtPath ? gOrigContentsAtPath(self, _cmd, path) : nil;
    if (CGMIsTargetPath(path)) { return CGMInjectedData(d, path); }
    CGMNoteJSReadOnce(path);
    return d;"""),

("""    NSString *s = gOrigStringContents ? gOrigStringContents(self, _cmd, path, enc, err) : nil;
    if (CGMIsTargetPath(path) && s.length) {""",
 """    NSString *s = gOrigStringContents ? gOrigStringContents(self, _cmd, path, enc, err) : nil;
    if (!CGMIsTargetPath(path)) { CGMNoteJSReadOnce(path); return s; }
    if (s.length) {"""),
]

for old, new in pairs:
    assert old in s, "pattern missing:\n" + old[:90]
    s = s.replace(old, new, 1)
    n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched %d hook sites, size %d" % (n, len(s)))
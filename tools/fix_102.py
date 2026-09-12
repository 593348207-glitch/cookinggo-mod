import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()

bad = "/* ============================== mailbox/* ============================== mailbox =================================== */"
assert bad in s, "mangled marker not found"

good = r'''/* ============================== write helpers ============================= */

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

/* ============================== mailbox =================================== */'''

s = s.replace(bad, good, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("fixed, size", len(s))

# sanity: all required symbols present
import re
for sym in ["CGMWriteData", "CGMWriteString", "CGMWriteJSON", "CGMReadJSON", "CGMReadConfig",
            "gCfgPosix", "gCfgObjc", "gCfgOverlay", "CGMStartTick", "CGMOnLaunchDone",
            "CGMRedirectPath", "CGMInstallPOSIXHooks", "CGMInstallObjCHooks", "CGMEnsureMailbox"]:
    print("%-22s %d" % (sym, len(re.findall(re.escape(sym), s))))
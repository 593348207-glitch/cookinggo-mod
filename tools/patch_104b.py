import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()

old = """        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }
        [gVC refreshStatus];"""
new = """        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }

        /* Hook-hit telemetry: tells us which file-read surface the engine uses. */
        {
            static int lastReported[kCGMHitCount];
            static int reportBudget = 40;
            NSMutableArray *parts = [NSMutableArray array];
            BOOL changed = NO;
            for (int i = 0; i < kCGMHitCount; i++) {
                int v = gHits[i];
                if (v > 0) { [parts addObject:[NSString stringWithFormat:@"%s=%d", kCGMHitNames[i], v]]; }
                if (v != lastReported[i]) { changed = YES; lastReported[i] = v; }
            }
            if (changed && reportBudget-- > 0) {
                CGMLog(@"hook hits: %@", parts.count ? [parts componentsJoinedByString:@" "] : @"(none)");
                [gVC appendLog:[NSString stringWithFormat:@"[hits] %@",
                                parts.count ? [parts componentsJoinedByString:@" "] : @"(none)"]];
            }
            static int lastSig = -1;
            int sig = 0;
            for (int i = 0; i < kCGMHitCount; i++) { sig = sig * 31 + gHits[i]; }
            if (sig != lastSig || lastSig == -1) {
                lastSig = sig;
                NSMutableDictionary *d = [NSMutableDictionary dictionary];
                for (int i = 0; i < kCGMHitCount; i++) {
                    d[[NSString stringWithUTF8String:kCGMHitNames[i]]] = @(gHits[i]);
                }
                d[@"injected"] = @(gInjectLogDone);
                d[@"tempCopy"] = @(gTempScriptPath != nil);
                CGMWriteJSON(d, [gChosenMailbox stringByAppendingPathComponent:@"hits.json"]);
            }
        }
        [gVC refreshStatus];"""
assert old in s, "tick anchor missing"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("tick telemetry added, size", len(s))
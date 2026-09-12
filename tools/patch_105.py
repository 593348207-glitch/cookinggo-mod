import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
old = "        [gVC refreshStatus];\n    } @catch (NSException *e) {\n        CGMLog(@\"tick exception: %@\", e.reason);"
new = """        /* If the on-disk bootstrap is missing (e.g. the game was updated and the
           script was replaced), say so instead of failing silently. */
        static int earlyTicks = 0;
        if (!gInjectLogDone && !hello) {
            earlyTicks++;
            if (earlyTicks == 40) {
                CGMLog(@"WARNING: no JS bootstrap seen. If the game was updated, reinstall com.seagull.cookinggomod.");
                [gVC appendLog:@"⚠ 未检测到 JS bootstrap：游戏更新过的话，重装本 DEB 即可。"];
            }
        }

        [gVC refreshStatus];
    } @catch (NSException *e) {
        CGMLog(@"tick exception: %@", e.reason);"""
assert old in s, "tick tail anchor missing"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("warning hint added, size", len(s))
import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# 1. verbose-view flag, declared before the logging section uses it ------------
s = s.replace('''/* ============================== logging =================================== */''',
'''/* ============================== logging =================================== */

/* When 0, native diagnostics go to NSLog + mod.log only. The on-screen log area
   then carries just the operator-facing results (修改前 / 输入表达 / 修改后 and
   the JS receipts). Set vlog=1 to mirror the diagnostics into the panel again. */
static int gCfgVerboseLog = 0;''', 1); n += 1

# 2. gate the on-screen mirror in CGMLog --------------------------------------
old = '''    if (!gLogStore) { gLogStore = [NSMutableArray array]; }
    [gLogStore addObject:body];
    if (gLogStore.count > 400) { [gLogStore removeObjectAtIndex:0]; }
    CGMFileAppend(line);
    if (gLogSink) {
        NSString *copy = [body copy];
        dispatch_async(dispatch_get_main_queue(), ^{ gLogSink(copy); });
    }
}'''
new = '''    CGMFileAppend(line);
    if (!gCfgVerboseLog) { return; }
    if (!gLogStore) { gLogStore = [NSMutableArray array]; }
    [gLogStore addObject:body];
    if (gLogStore.count > 400) { [gLogStore removeObjectAtIndex:0]; }
    if (gLogSink) {
        NSString *copy = [body copy];
        dispatch_async(dispatch_get_main_queue(), ^{ gLogSink(copy); });
    }
}'''
assert old in s, "CGMLog anchor missing"
s = s.replace(old, new, 1); n += 1

# 3. do not replay the stored diagnostics into a fresh panel ------------------
s = s.replace('''    gLogSink = ^(NSString *line) { [weakSelf appendLog:line]; };
    if (gLogStore.count) { for (NSString *l in [gLogStore copy]) { [self appendLog:l]; } }''',
'''    gLogSink = ^(NSString *line) { [weakSelf appendLog:line]; };''', 1); n += 1

# 4. cfg key ---------------------------------------------------------------
s = s.replace('static int gCfgRot = 0;      /* rotate the overlay to match the game\'s drawing  */',
              'static int gCfgRot = 0;      /* rotate the overlay to match the game\'s drawing  */\nstatic int gCfgVerboseLogCfg = 0;', 1)
s = s.replace('    else if (strcmp(key, "rot") == 0) { gCfgRot = atoi(eq + 1); }',
              '    else if (strcmp(key, "rot") == 0) { gCfgRot = atoi(eq + 1); }\n    else if (strcmp(key, "vlog") == 0) { gCfgVerboseLogCfg = val; }', 1)
s = s.replace('    CGMLog(@"config: objc=%d posix=%d overlay=%d panel=%d rot=%d", gCfgObjc, gCfgPosix, gCfgOverlay, gCfgPanelOpen, gCfgRot);',
              '    gCfgVerboseLog = gCfgVerboseLogCfg;\n    CGMLog(@"config: objc=%d posix=%d overlay=%d panel=%d rot=%d vlog=%d",\n           gCfgObjc, gCfgPosix, gCfgOverlay, gCfgPanelOpen, gCfgRot, gCfgVerboseLog);', 1)
n += 3

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["gCfgVerboseLog", "vlog"]:
    print(k, "->", s.count(k))
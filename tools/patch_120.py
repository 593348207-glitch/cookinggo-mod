import io, re
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# Wrap the diagnostic appendLog blocks in CGMTick with the vlog gate.
old_probe = '''        NSDictionary *probe = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"probe.json"]);
        if (probe) {'''
new_probe = '''        NSDictionary *probe = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"probe.json"]);
        if (probe && gCfgVerboseLog) {'''
assert old_probe in s, "probe anchor"
s = s.replace(old_probe, new_probe, 1); n += 1

# gate the hook-hit log line that goes to the visible log
old_hits = '''                [gVC appendLog:[NSString stringWithFormat:@"[hits] %@",
                                parts.count ? [parts componentsJoinedByString:@" "] : @"(none)"]];'''
if old_hits in s:
    s = s.replace(old_hits, '''                if (gCfgVerboseLog) {
                    [gVC appendLog:[NSString stringWithFormat:@"[hits] %@",
                                    parts.count ? [parts componentsJoinedByString:@" "] : @"(none)"]];
                }''', 1); n += 1

# gate the "waiting for engine" line
old_wait = '''        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }'''
if old_wait in s:
    s = s.replace(old_wait, '''        if (hello && !gEngineReady && gCfgVerboseLog) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }''', 1); n += 1

# gate the "[JS] bootstrap 已到达" line
old_boot = '''        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap 已到达 v%@，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }'''
if old_boot in s:
    s = s.replace(old_boot, '''        if (hello && !gEngineReady && gCfgVerboseLog) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap 已到达 v%@，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }''', 1); n += 1

# gate the missing-bootstrap warning
old_warn = '''                [gVC appendLog:@"⚠ 未检测到 JS bootstrap：游戏更新过的话，重装本 DEB 即可。"];'''
if old_warn in s:
    s = s.replace(old_warn, '''                if (gCfgVerboseLog) {
                    [gVC appendLog:@"⚠ 未检测到 JS bootstrap：游戏更新过的话，重装本 DEB 即可。"];
                }''', 1); n += 1

# start the visible log with the operator-facing header once
s = s.replace('''    gLogSink = ^(NSString *line) { [weakSelf appendLog:line]; };''',
'''    gLogSink = ^(NSString *line) { [weakSelf appendLog:line]; };
    [self appendLog:[NSString stringWithFormat:@"CookingGoMod v%@ | 选资源 → 输数字 → + 或 =", CGM_VERSION]];''', 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["gCfgVerboseLog", "[hits]"]:
    print(k, "->", s.count(k))
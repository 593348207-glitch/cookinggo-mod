import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# 1. counters instead of logging every touch ----------------------------------
s = s.replace('''static volatile int gHits[kCGMHitCount];''',
'''static volatile int gHits[kCGMHitCount];
static volatile int gWindowTouchesBegan;   /* every touch the overlay window sees */
static volatile int gBallTouchesBegan;     /* touches that actually landed on the ball */''', 1); n += 1

old = '''    for (UITouch *t in event.allTouches) {
        if (t.phase == UITouchPhaseBegan) {
            CGMLog(@"window touch began at %.0f,%.0f (type=%ld)",
                   [t locationInView:self].x, [t locationInView:self].y, (long)t.type);
        }
    }
    [super sendEvent:event];'''
new = '''    /* Counted, never logged per event: the old version appended a line to
       mod.log for every touch and that log was rendered into the on-screen
       debug view, which produced thousands of lines of noise. */
    for (UITouch *t in event.allTouches) {
        if (t.phase == UITouchPhaseBegan) {
            __sync_fetch_and_add(&gWindowTouchesBegan, 1);
        }
    }
    [super sendEvent:event];'''
assert old in s, "window sendEvent anchor missing"
s = s.replace(old, new, 1); n += 1

# 2. ball touch down: count, do not log ---------------------------------------
s = s.replace('''    CGMLog(@"touch down on ball (ball=%.0f,%.0f touch=%.0f,%.0f)", b.center.x, b.center.y, p.x, p.y);''',
'''    __sync_fetch_and_add(&gBallTouchesBegan, 1);''', 1); n += 1

# 3. expose the counters in hits.json -----------------------------------------
s = s.replace('''                d[@"injected"] = @(gInjectLogDone);
                d[@"tempCopy"] = @(gTempScriptPath != nil);''',
'''                d[@"injected"] = @(gInjectLogDone);
                d[@"tempCopy"] = @(gTempScriptPath != nil);
                d[@"windowTouchBegan"] = @(gWindowTouchesBegan);
                d[@"ballTouchBegan"] = @(gBallTouchesBegan);''', 1); n += 1

# 4. hook-hit telemetry must not write to mod.log every second ----------------
s = s.replace('''                CGMLog(@"hook hits: %@", parts.count ? [parts componentsJoinedByString:@" "] : @"(none)");''',
'''                /* hits.json only - keep mod.log readable. */''', 1); n += 1

# 5. drop the remaining per-status chatter from the visible log ---------------
s = s.replace('''        if (hello && !gEngineReady) {
            [gVC appendLog:[NSString stringWithFormat:@"[JS] bootstrap v%@ 已注入，等待引擎 init",
                            hello[@"version"] ?: @"?"]];
        }''',
'''        /* Status chatter stays out of the visible log; mod.log / ui_state.json
           carry the live state. */''', 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["gWindowTouchesBegan","gBallTouchesBegan","hook hits"]:
    print(k, "->", s.count(k))
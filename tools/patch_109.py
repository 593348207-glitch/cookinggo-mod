import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# --- properties --------------------------------------------------------------
s = s.replace("@property (nonatomic, assign) BOOL didInitPositions;",
              "@property (nonatomic, assign) CGPoint ballTouchOffset;\n@property (nonatomic, assign) BOOL ballDragMoved;\n@property (nonatomic, assign) BOOL didInitPositions;", 1)
n += 1

# --- ball: keep the pan recognizer, add UIControl drag tracking ---------------
old_tail = """    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(dragBall:)];
    [self.ball addGestureRecognizer:pan];
    [self.stage addSubview:self.ball];
}"""
new_tail = """    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(dragBall:)];
    [self.ball addGestureRecognizer:pan];

    /* UIControl's own drag tracking is far more dependable than a pan
       recognizer on a button, and it reports through the same responder path
       as the taps that already worked on device. */
    [self.ball addTarget:self action:@selector(ballTouchDown:withEvent:) forControlEvents:UIControlEventTouchDown];
    [self.ball addTarget:self action:@selector(ballTouchMoved:withEvent:)
        forControlEvents:(UIControlEventTouchDragInside | UIControlEventTouchDragOutside |
                            UIControlEventTouchDragEnter | UIControlEventTouchDragExit)];
    [self.ball addTarget:self action:@selector(ballTouchUp:withEvent:)
        forControlEvents:(UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel)];

    [self.stage addSubview:self.ball];
}

- (void)ballTouchDown:(UIButton *)b withEvent:(UIEvent *)e {
    UITouch *t = e.allTouches.anyObject;
    if (!t) { return; }
    CGPoint p = [t locationInView:self.stage];
    self.ballTouchOffset = CGPointMake(b.center.x - p.x, b.center.y - p.y);
    self.ballDragMoved = NO;
    CGMLog(@"touch down on ball (ball=%.0f,%.0f touch=%.0f,%.0f)", b.center.x, b.center.y, p.x, p.y);
}

- (void)ballTouchMoved:(UIButton *)b withEvent:(UIEvent *)e {
    UITouch *t = e.allTouches.anyObject;
    if (!t) { return; }
    CGPoint p = [t locationInView:self.stage];
    CGPoint c = CGPointMake(p.x + self.ballTouchOffset.x, p.y + self.ballTouchOffset.y);
    if (!self.ballDragMoved) {
        CGFloat dx = fabs(c.x - b.center.x), dy = fabs(c.y - b.center.y);
        if (dx + dy > 6.0) { self.ballDragMoved = YES; }
    }
    if (self.ballDragMoved) { [self placeBall:c]; }
}

- (void)ballTouchUp:(UIButton *)b withEvent:(UIEvent *)e {
    if (self.ballDragMoved) {
        CGMLog(@"drag end -> ball=%.0f,%.0f", b.center.x, b.center.y);
        [self persistBallPosition];
    }
    self.ballDragMoved = NO;
}

- (void)placeBall:(CGPoint)c {
    CGRect safe = [self safeFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    c.x = MAX(CGRectGetMinX(safe) + r, MIN(CGRectGetMaxX(safe) - r, c.x));
    c.y = MAX(CGRectGetMinY(safe) + r, MIN(CGRectGetMaxY(safe) - r, c.y));
    self.ball.center = c;
    self.ballCenter = c;
    [self writeUIState];
}

- (void)persistBallPosition {
    if (!gMailboxPath) { return; }
    CGMWriteJSON(@{ @"x": @(self.ball.center.x), @"y": @(self.ball.center.y) },
                 [gMailboxPath stringByAppendingPathComponent:@"ball_pos.json"]);
}

- (void)restoreBallPosition {
    if (!gMailboxPath) { return; }
    NSDictionary *d = CGMReadJSON([gMailboxPath stringByAppendingPathComponent:@"ball_pos.json"]);
    if (![d isKindOfClass:[NSDictionary class]]) { return; }
    id x = d[@"x"], y = d[@"y"];
    if (![x isKindOfClass:[NSNumber class]] || ![y isKindOfClass:[NSNumber class]]) { return; }
    [self placeBall:CGPointMake([x doubleValue], [y doubleValue])];
    CGMLog(@"restored ball position %.0f,%.0f", [x doubleValue], [y doubleValue]);
}"""
assert old_tail in s, "ball tail anchor missing"
s = s.replace(old_tail, new_tail, 1)
n += 1

# --- pan gesture: same direction handling + logging --------------------------
s = s.replace("""- (void)dragBall:(UIPanGestureRecognizer *)g {
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
}""",
"""- (void)dragBall:(UIPanGestureRecognizer *)g {
    /* translation arrives in view space; the ball lives in the (possibly
       rotated) stage, so rotate the delta into stage space first. */
    CGPoint t = [g translationInView:self.view];
    if (gCfgRot == 90)       { CGPoint r90 = CGPointMake(-t.y,  t.x); t = r90; }
    else if (gCfgRot == 180) { CGPoint r180 = CGPointMake(-t.x, -t.y); t = r180; }
    else if (gCfgRot == 270 || gCfgRot == -90) { CGPoint r270 = CGPointMake(t.y, -t.x); t = r270; }
    [g setTranslation:CGPointZero inView:self.view];
    CGPoint c = CGPointMake(self.ball.center.x + t.x, self.ball.center.y + t.y);
    self.ballDragMoved = YES;
    [self placeBall:c];
}""", 1)
n += 1

# --- restore on first layout -------------------------------------------------
s = s.replace("""    if (!self.didInitPositions) {
        self.didInitPositions = YES;
        self.ballCenter = CGPointMake(CGRectGetMaxX(safe) - 40.0, CGRectGetMidY(safe) - 40.0);
        self.panelCenter = CGPointMake(CGRectGetMidX(safe), CGRectGetMidY(safe));
    }""",
"""    if (!self.didInitPositions) {
        self.didInitPositions = YES;
        self.ballCenter = CGPointMake(CGRectGetMaxX(safe) - 40.0, CGRectGetMidY(safe) - 40.0);
        self.panelCenter = CGPointMake(CGRectGetMidX(safe), CGRectGetMidY(safe));
        [self restoreBallPosition];
    }""", 1)
n += 1

# --- declare new VC methods --------------------------------------------------
s = s.replace("- (void)setPanelVisible:(BOOL)visible;\n- (void)writeUIState;",
              "- (void)setPanelVisible:(BOOL)visible;\n- (void)writeUIState;\n- (void)placeBall:(CGPoint)c;\n- (void)persistBallPosition;\n- (void)restoreBallPosition;", 1)
n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["ballTouchMoved","placeBall","restoreBallPosition","persistBallPosition","dragBall"]:
    print(k, s.count(k))
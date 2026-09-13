import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# ---- 1. UISegmentedControl: correct font API --------------------------------
s = s.replace('        self.resSeg.titleTextAttributes = @{ NSFontAttributeName: [UIFont boldSystemFontOfSize:12.0] };',
'''        [self.resSeg setTitleTextAttributes:@{ NSFontAttributeName: [UIFont boldSystemFontOfSize:12.0] }
                                   forState:UIControlStateNormal];''', 1)
n += 1

# ---- 2. drop the pan recognizer on the ball ---------------------------------
old_pan = '''    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(dragBall:)];
    [self.ball addGestureRecognizer:pan];

    /* UIControl's own drag tracking is far more dependable than a pan
       recognizer on a button, and it reports through the same responder path
       as the taps that already worked on device. */'''
new_pan = '''    /* Only UIControl tracking drives the ball. A UIPanGestureRecognizer was
       attached as well in 1.0.9 and both paths moved the ball at once; the pan
       path works in view space and needed a manual rotation, so the two fought
       each other and the ball travelled backwards on the rotated stage.
       UIControl reports in stage space already, so it is correct on its own. */'''
assert old_pan in s, "pan block missing"
s = s.replace(old_pan, new_pan, 1)
n += 1

# ---- 3. delete dragBall:, keep dragPanel: ----------------------------------
i = s.find("- (void)dragBall:(UIPanGestureRecognizer *)g {")
j = s.find("- (void)dragPanel:(UIPanGestureRecognizer *)g {")
assert i > 0 and j > i, "dragBall block bounds"
s = s[:i] + s[j:]
n += 1

# ---- 4. snapping -------------------------------------------------------------
old_up = '''- (void)ballTouchUp:(UIButton *)b withEvent:(UIEvent *)e {
    if (self.ballDragMoved) {
        CGMLog(@"drag end -> ball=%.0f,%.0f", b.center.x, b.center.y);
        [self persistBallPosition];
        [self writeUIState];
    }
    self.ballDragMoved = NO;
}'''
new_up = '''- (void)ballTouchUp:(UIButton *)b withEvent:(UIEvent *)e {
    if (self.ballDragMoved) {
        [self snapBallToNearestEdge];
    }
    self.ballDragMoved = NO;
}

/* Drag is free, release snaps the ball to whichever side it is closer to.
   The vertical position is kept, so it stays wherever it was put. */
- (void)snapBallToNearestEdge {
    CGRect safe = [self safeFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    CGFloat margin = 6.0;
    CGFloat leftX  = CGRectGetMinX(safe) + r + margin;
    CGFloat rightX = CGRectGetMaxX(safe) - r - margin;
    CGFloat targetX = (fabs(self.ball.center.x - leftX) <= fabs(self.ball.center.x - rightX)) ? leftX : rightX;
    CGPoint c = CGPointMake(targetX, self.ball.center.y);
    c.y = MAX(CGRectGetMinY(safe) + r + margin, MIN(CGRectGetMaxY(safe) - r - margin, c.y));
    CGMLog(@"snap ball -> %.0f,%.0f", c.x, c.y);
    self.ballCenter = c;
    [UIView animateWithDuration:0.22
                          delay:0
                        options:(UIViewAnimationOptionBeginFromCurrentState | UIViewAnimationOptionCurveEaseOut)
                     animations:^{
        self.ball.center = c;
    } completion:^(BOOL finished) {
        [self persistBallPosition];
        [self writeUIState];
    }];
}'''
assert old_up in s, "ballTouchUp block missing"
s = s.replace(old_up, new_up, 1)
n += 1

# ---- 5. default position = left edge, vertically centred --------------------
old_pos = '        self.ballCenter = CGPointMake(CGRectGetMaxX(safe) - 40.0, CGRectGetMidY(safe) - 40.0);'
new_pos = ('        /* Default: snapped to the left edge, vertically centred - the game\n'
           '           keeps its own buttons on the right side of the layout. */\n'
           '        self.ballCenter = CGPointMake(CGRectGetMinX(safe) + 33.0, CGRectGetMidY(safe));')
assert old_pos in s, "default position anchor missing"
s = s.replace(old_pos, new_pos, 1)
n += 1

# ---- 6. restoreBallPosition also snaps -------------------------------------
old_res = '''    [self placeBall:CGPointMake([x doubleValue], [y doubleValue])];
    CGMLog(@"restored ball position %.0f,%.0f", [x doubleValue], [y doubleValue]);'''
new_res = '''    [self placeBall:CGPointMake([x doubleValue], [y doubleValue])];
    [self snapBallToNearestEdge];
    CGMLog(@"restored ball position %.0f,%.0f", self.ball.center.x, self.ball.center.y);'''
assert old_res in s, "restore anchor missing"
s = s.replace(old_res, new_res, 1)
n += 1

# ---- 7. declare the new method ----------------------------------------------
s = s.replace("- (void)persistBallPosition;\n- (void)restoreBallPosition;",
              "- (void)persistBallPosition;\n- (void)restoreBallPosition;\n- (void)snapBallToNearestEdge;", 1)
n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["snapBallToNearestEdge", "dragBall", "titleTextAttributes", "UIPanGestureRecognizer"]:
    print(k, "->", s.count(k))
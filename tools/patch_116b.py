import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

s = s.replace('''- (void)persistBallPosition {''',
'''/* Re-applying the default on every layout while no stored position exists is
   deliberate: the first layout pass can run before the window geometry settles,
   which left the ball parked in the wrong place in 1.1.5. It is idempotent, and
   as soon as the operator drags the ball the stored file takes over. */
- (void)applyDefaultBallIfNeeded {
    if (!gMailboxPath) { return; }
    static BOOL hasStored = NO;
    static BOOL checkedOnce = NO;
    if (!checkedOnce) {
        checkedOnce = YES;
        hasStored = [[NSFileManager defaultManager]
                     fileExistsAtPath:[gMailboxPath stringByAppendingPathComponent:@"ball_pos.json"]];
        CGMLog(@"ball position store present=%d", hasStored);
    }
    if (hasStored) { return; }
    CGRect sv = [self safeViewFrame];
    if (sv.size.width < 20 || sv.size.height < 20) { return; }
    CGFloat vr = 27.0 + 6.0;
    CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
    [self placeBall:[self stagePointForViewPoint:want]];
}

- (void)persistBallPosition {''', 1); n += 1

old = '''        /* Default: the edge the operator sees on their left, vertically
           centred. Stated in view space and converted, so it is correct for any
           rot value without reasoning about which stage axis maps where. */
        CGRect sv = [self safeViewFrame];
        CGFloat vr = 27.0 + 6.0;
        CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
        CGPoint sp = [self stagePointForViewPoint:want];
        CGMLog(@"default ball: view %.0f,%.0f -> stage %.0f,%.0f", want.x, want.y, sp.x, sp.y);
        [self placeBall:sp];
        self.panelCenter'''
new = '''        self.panelCenter'''
assert old in s, "init default anchor missing"
s = s.replace(old, new, 1); n += 1

old2 = '''    [self applyDefaultBallIfNeeded];
    self.ball.center = self.ballCenter;'''
if old2 not in s:
    old2b = '''    self.ball.center = self.ballCenter;'''
    assert old2b in s, "layout ball anchor missing"
    s = s.replace(old2b, '''    [self applyDefaultBallIfNeeded];
    self.ball.center = self.ballCenter;''', 1)
    n += 1

s = s.replace('''- (void)persistBallPosition {
    if (!gMailboxPath) { return; }''',
'''- (void)persistBallPosition {
    if (!gMailboxPath) { return; }
    CGMLog(@"ball position stored at view %.0f,%.0f",
           [self viewPointForStagePoint:self.ball.center].x,
           [self viewPointForStagePoint:self.ball.center].y);''', 1); n += 1

s = s.replace('''    [self snapBallToNearestEdge];
    CGMLog(@"restored ball position %.0f,%.0f", self.ball.center.x, self.ball.center.y);''',
'''    [self snapBallToNearestEdge];
    CGMLog(@"restored ball position -> view %.0f,%.0f",
           [self viewPointForStagePoint:self.ball.center].x,
           [self viewPointForStagePoint:self.ball.center].y);''', 1); n += 1

s = s.replace("- (void)snapBallToNearestEdge;", "- (void)snapBallToNearestEdge;\n- (void)applyDefaultBallIfNeeded;", 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
print("applyDefaultBallIfNeeded ->", s.count("applyDefaultBallIfNeeded"))
print("applyDefaultBallIfNeeded call in layout ->", s.count("[self applyDefaultBallIfNeeded]"))
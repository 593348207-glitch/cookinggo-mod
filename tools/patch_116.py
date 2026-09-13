import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# --- helper: apply default while no stored position exists -------------------
s = s.replace('''- (void)persistBallPosition {''',
'''/* Re-applying the default on every layout while no stored position exists is
   deliberate: the first layout pass can run before the window geometry settles,
   which left the ball parked off to one side (1.1.5). It is idempotent, and as
   soon as the operator drags the ball the stored file takes over. */
- (void)applyDefaultBallIfNeeded {
    if (!gMailboxPath) { return; }
    static BOOL hasStored = NO;
    static BOOL checkedOnce = NO;
    if (!checkedOnce) {
        checkedOnce = YES;
        hasStored = ([[NSFileManager defaultManager]
                      fileExistsAtPath:[gMailboxPath stringByAppendingPathComponent:@"ball_pos.json"]]);
        CGMLog(@"ball position store present=%d", hasStored);
    }
    if (hasStored) { return; }
    CGRect sv = [self safeViewFrame];
    if (sv.size.width < 20 || sv.size.height < 20) { return; }
    CGFloat vr = 27.0 + 6.0;
    CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
    CGPoint sp = [self stagePointForViewPoint:want];
    [self placeBall:sp];
}

- (void)persistBallPosition {''', 1); n += 1

# --- drop the one-shot default from the initial-position block ---------------
old = '''        CGRect sv = [self safeViewFrame];
        CGFloat vr = 27.0 + 6.0;
        CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
        CGPoint sp = [self stagePointForViewPoint:want];
        CGMLog(@"default ball: view %.0f,%.0f -> stage %.0f,%.0f", want.x, want.y, sp.x, sp.y);
        [self placeBall:sp];
        [self restoreBallPosition];'''
new = '''        [self restoreBallPosition];'''
assert old in s, "init default anchor missing"
s = s.replace(old, new, 1); n += 1

# --- call it every layout, after restore --------------------------------------
old2 = '''    self.ball.center = self.ballCenter;

    self.header.frame = CGRectMake(0, 0, panelW, headerH);'''
new2 = '''    [self applyDefaultBallIfNeeded];
    self.ball.center = self.ballCenter;

    self.header.frame = CGRectMake(0, 0, panelW, headerH);'''
assert old2 in s, "layout call anchor missing"
s = s.replace(old2, new2, 1); n += 1

# --- persistBallPosition should mark the store as existing -------------------
s = s.replace('''- (void)persistBallPosition {
    if (!gMailboxPath) { return; }''',
'''- (void)persistBallPosition {
    if (!gMailboxPath) { return; }
    CGMLog(@"ball position stored at view %.0f,%.0f",
           [self viewPointForStagePoint:self.ball.center].x,
           [self viewPointForStagePoint:self.ball.center].y);''', 1); n += 1

# --- mark store as present after persisting (so default stops fighting) ------
s = s.replace('''    [self snapBallToNearestEdge];
    CGMLog(@"restored ball position %.0f,%.0f", self.ball.center.x, self.ball.center.y);''',
'''    [self snapBallToNearestEdge];
    CGMLog(@"restored ball position -> view %.0f,%.0f",
           [self viewPointForStagePoint:self.ball.center].x,
           [self viewPointForStagePoint:self.ball.center].y);''', 1); n += 1

# --- declare the helper -------------------------------------------------------
s = s.replace("- (void)snapBallToNearestEdge;", "- (void)snapBallToNearestEdge;\n- (void)applyDefaultBallIfNeeded;", 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["applyDefaultBallIfNeeded","ball position store present"]:
    print(k, "->", s.count(k))
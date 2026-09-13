import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# ---------------------------------------------------------------- stage class
old = "@interface CGMWindow : UIWindow\n@end"
new = '''/* The stage only exists to be rotated; it must NOT be a touch target.
   It covers the whole screen, and a plain UIView there swallows every touch,
   which is what made the game's own buttons dead from 1.0.8 onwards. Only the
   ball and the panel are interactive. */
@interface CGMStageView : UIView
@end

@implementation CGMStageView
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    for (UIView *sub in [self.subviews reverseObjectEnumerator]) {
        if (sub.hidden || sub.alpha < 0.01 || !sub.userInteractionEnabled) { continue; }
        CGPoint p = [sub convertPoint:point fromView:self];
        UIView *v = [sub hitTest:p withEvent:event];
        if (v) { return v; }
    }
    return nil;
}
@end

@interface CGMWindow : UIWindow
@end'''
assert old in s, "window interface anchor missing"
s = s.replace(old, new, 1); n += 1

s = s.replace("    self.stage = [[UIView alloc] initWithFrame:CGRectZero];",
              "    self.stage = [[CGMStageView alloc] initWithFrame:CGRectZero];", 1); n += 1
s = s.replace("@property (nonatomic, strong) UIView *stage;",
              "@property (nonatomic, strong) CGMStageView *stage;", 1); n += 1

# ---------------------------------------------------------------- view helpers
old2 = '''- (void)layoutStage {'''
new2 = '''/* Unrotated safe frame, i.e. what the operator actually sees. */
- (CGRect)safeViewFrame {
    CGRect b = self.view.bounds;
    if (@available(iOS 11.0, *)) {
        UIEdgeInsets in = self.view.safeAreaInsets;
        b.origin.x += in.left; b.origin.y += in.top;
        b.size.width -= (in.left + in.right);
        b.size.height -= (in.top + in.bottom);
    }
    return b;
}

- (CGPoint)viewPointForStagePoint:(CGPoint)sp {
    return CGPointApplyAffineTransform(sp, self.stage.transform);
}

- (CGPoint)stagePointForViewPoint:(CGPoint)vp {
    return CGPointApplyAffineTransform(vp, CGAffineTransformInvert(self.stage.transform));
}

- (void)layoutStage {'''
assert old2 in s, "layoutStage anchor missing"
s = s.replace(old2, new2, 1); n += 1

# ---------------------------------------------------------------- default pos
old3 = '''        /* Default: snapped to the left edge, vertically centred - the game
           keeps its own buttons on the right side of the layout. */
        self.ballCenter = CGPointMake(CGRectGetMinX(safe) + 33.0, CGRectGetMidY(safe));'''
new3 = '''        /* Default: the edge the operator sees on their left, vertically
           centred. The stage is rotated, so the target is computed in view
           space and converted back instead of guessing an axis. */
        CGRect sv = [self safeViewFrame];
        CGFloat vr = 27.0 + 6.0;
        CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
        CGPoint sp = [self stagePointForViewPoint:want];
        self.ballCenter = sp;'''
assert old3 in s, "default pos anchor missing"
s = s.replace(old3, new3, 1); n += 1

# ---------------------------------------------------------------- snapping
old4 = '''- (void)snapBallToNearestEdge {
    CGRect safe = [self safeFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    CGFloat margin = 6.0;
    CGFloat leftX  = CGRectGetMinX(safe) + r + margin;
    CGFloat rightX = CGRectGetMaxX(safe) - r - margin;
    CGFloat targetX = (fabs(self.ball.center.x - leftX) <= fabs(self.ball.center.x - rightX)) ? leftX : rightX;
    CGPoint c = CGPointMake(targetX, self.ball.center.y);
    c.y = MAX(CGRectGetMinY(safe) + r + margin, MIN(CGRectGetMaxY(safe) - r - margin, c.y));
    CGMLog(@"snap ball -> %.0f,%.0f", c.x, c.y);
    self.ballCenter = c;'''
new4 = '''- (void)snapBallToNearestEdge {
    CGFloat r = self.ball.bounds.size.width / 2.0;
    CGFloat margin = 6.0;
    CGRect sv = [self safeViewFrame];
    /* Decide in view space: with a rotated stage the ball's own axes do not
       match the edges the operator sees. */
    CGPoint cur = [self viewPointForStagePoint:self.ball.center];
    CGFloat leftX  = CGRectGetMinX(sv) + r + margin;
    CGFloat rightX = CGRectGetMaxX(sv) - r - margin;
    CGFloat targetX = (fabs(cur.x - leftX) <= fabs(cur.x - rightX)) ? leftX : rightX;
    CGFloat targetY = MAX(CGRectGetMinY(sv) + r + margin, MIN(CGRectGetMaxY(sv) - r - margin, cur.y));
    CGPoint c = [self stagePointForViewPoint:CGPointMake(targetX, targetY)];
    CGMLog(@"snap ball -> view %.0f,%.0f (stage %.0f,%.0f)", targetX, targetY, c.x, c.y);
    self.ballCenter = c;'''
assert old4 in s, "snap anchor missing"
s = s.replace(old4, new4, 1); n += 1

# ---------------------------------------------------------------- placeBall clamp in view space
old5 = '''- (void)placeBall:(CGPoint)c {
    CGRect safe = [self safeFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    c.x = MAX(CGRectGetMinX(safe) + r, MIN(CGRectGetMaxX(safe) - r, c.x));
    c.y = MAX(CGRectGetMinY(safe) + r, MIN(CGRectGetMaxY(safe) - r, c.y));
    self.ball.center = c;
    self.ballCenter = c;
}'''
new5 = '''- (void)placeBall:(CGPoint)c {
    /* Clamp in view space so the ball can never be dragged off the visible
       screen, regardless of the stage rotation. */
    CGRect sv = [self safeViewFrame];
    CGFloat r = self.ball.bounds.size.width / 2.0;
    CGPoint v = [self viewPointForStagePoint:c];
    v.x = MAX(CGRectGetMinX(sv) + r, MIN(CGRectGetMaxX(sv) - r, v.x));
    v.y = MAX(CGRectGetMinY(sv) + r, MIN(CGRectGetMaxY(sv) - r, v.y));
    CGPoint clamped = [self stagePointForViewPoint:v];
    self.ball.center = clamped;
    self.ballCenter = clamped;
}'''
assert old5 in s, "placeBall anchor missing"
s = s.replace(old5, new5, 1); n += 1

# ---------------------------------------------------------------- init order
s = s.replace('''    if (!self.didInitPositions) {
        self.didInitPositions = YES;''',
'''    if (!self.didInitPositions) {
        self.didInitPositions = YES;''', 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["CGMStageView","safeViewFrame","stagePointForViewPoint","viewPointForStagePoint"]:
    print(k, "->", s.count(k))
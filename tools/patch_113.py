import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()

old = '''        /* Default: the edge the operator sees on their left, vertically
           centred. The stage is rotated, so the target is computed in view
           space and converted back instead of guessing an axis. */
        CGRect sv = [self safeViewFrame];
        CGFloat vr = 27.0 + 6.0;
        CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
        CGPoint sp = [self stagePointForViewPoint:want];
        self.ballCenter = sp;'''
new = '''        /* Default: whichever stage edge ends up on the operator's left once
           the rotation is applied. Rather than reasoning about the transform,
           both candidate edges are converted to view space and the leftmost is
           taken - that stays correct for any rot value or safe area. */
        CGFloat vr = 27.0 + 6.0;
        CGPoint candA = CGPointMake(CGRectGetMinX(safe) + vr, CGRectGetMidY(safe));
        CGPoint candB = CGPointMake(CGRectGetMaxX(safe) - vr, CGRectGetMidY(safe));
        CGFloat ax = [self viewPointForStagePoint:candA].x;
        CGFloat bx = [self viewPointForStagePoint:candB].x;
        CGMLog(@"default ball candidates: A=%.0f B=%.0f (stage %.0f,%.0f | %.0f,%.0f)",
               ax, bx, candA.x, candA.y, candB.x, candB.y);
        [self placeBall:(ax <= bx ? candA : candB)];'''
assert old in s, "default anchor missing"
s = s.replace(old, new, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("default position fixed, size", len(s))
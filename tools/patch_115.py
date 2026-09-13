import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# 1. stage must cover the whole window once rotated ---------------------------
old = '''    CGFloat angle = (CGFloat)gCfgRot * (CGFloat)M_PI / 180.0;
    CGRect area = [self safeFrame];
    self.stage.transform = CGAffineTransformIdentity;
    self.stage.bounds = CGRectMake(0, 0, area.size.width, area.size.height);
    self.stage.center = CGPointMake(CGRectGetMidX(vb), CGRectGetMidY(vb));
    if (gCfgRot != 0) { self.stage.transform = CGAffineTransformMakeRotation(angle); }'''
new = '''    CGFloat angle = (CGFloat)gCfgRot * (CGFloat)M_PI / 180.0;
    BOOL rotated = (gCfgRot != 0);
    /* The stage must span the FULL window after rotation. Sizing it from the
       safe frame shrank it (750pt across an 844pt window), so the outer edges
       of the screen could not be addressed at all - that is why both edge
       candidates collapsed onto the same point in 1.1.4. Safe-area padding is
       applied inside safeFrame instead. */
    CGSize stageSize = rotated ? CGSizeMake(vb.size.height, vb.size.width) : vb.size;
    self.stage.transform = CGAffineTransformIdentity;
    self.stage.bounds = CGRectMake(0, 0, stageSize.width, stageSize.height);
    self.stage.center = CGPointMake(CGRectGetMidX(vb), CGRectGetMidY(vb));
    if (rotated) { self.stage.transform = CGAffineTransformMakeRotation(angle); }'''
assert old in s, "layoutStage anchor missing"
s = s.replace(old, new, 1); n += 1

# 2. default position: convert the view-space left edge into stage space ------
old2 = '''        /* Default: whichever stage edge ends up on the operator's left once
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
new2 = '''        /* Default: the edge the operator sees on their left, vertically
           centred. Stated in view space and converted, so it is correct for any
           rot value without reasoning about which stage axis maps where. */
        CGRect sv = [self safeViewFrame];
        CGFloat vr = 27.0 + 6.0;
        CGPoint want = CGPointMake(CGRectGetMinX(sv) + vr, CGRectGetMidY(sv));
        CGPoint sp = [self stagePointForViewPoint:want];
        CGMLog(@"default ball: view %.0f,%.0f -> stage %.0f,%.0f", want.x, want.y, sp.x, sp.y);
        [self placeBall:sp];'''
assert old2 in s, "default anchor missing"
s = s.replace(old2, new2, 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
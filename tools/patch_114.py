import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
old = '''- (CGPoint)viewPointForStagePoint:(CGPoint)sp {
    return CGPointApplyAffineTransform(sp, self.stage.transform);
}

- (CGPoint)stagePointForViewPoint:(CGPoint)vp {
    return CGPointApplyAffineTransform(vp, CGAffineTransformInvert(self.stage.transform));
}'''
new = '''/* NOTE: `view.transform` holds only the rotation around the view's centre, so
   applying it to a point gives an offset, not a position - that mistake put the
   ball off screen in 1.1.3. Convert through the view hierarchy instead. */
- (CGPoint)viewPointForStagePoint:(CGPoint)sp {
    return [self.stage convertPoint:sp toView:self.view];
}

- (CGPoint)stagePointForViewPoint:(CGPoint)vp {
    return [self.view convertPoint:vp toView:self.stage];
}'''
assert old in s, "helper anchor missing"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("convert helpers fixed, size", len(s))
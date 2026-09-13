import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
old = '''- (void)dragPanel:(UIPanGestureRecognizer *)g {
    CGPoint t = [g translationInView:self.view];
    CGPoint c = self.panel.center;
    c.x += t.x; c.y += t.y;
    [g setTranslation:CGPointZero inView:self.view];'''
new = '''- (void)dragPanel:(UIPanGestureRecognizer *)g {
    /* Translation must be read in the same space the panel is positioned in.
       Using self.view here made the panel travel backwards on the rotated
       stage, exactly like the ball did before 1.1.1. */
    CGPoint t = [g translationInView:self.stage];
    CGPoint c = self.panel.center;
    c.x += t.x; c.y += t.y;
    [g setTranslation:CGPointZero inView:self.stage];'''
assert old in s, "dragPanel anchor missing"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("dragPanel fixed; size", len(s))
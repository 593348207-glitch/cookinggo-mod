import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# --- resource table: add 换装币 -------------------------------------------------
old = '''static NSString * const kCGMResKeys[]  = { @"gem", @"coin", @"power", @"adcoupon" };
static NSString * const kCGMResNames[] = { @"钻石", @"金币", @"燃油", @"免广告券" };
static const int kCGMResCount = 4;'''
new = '''/* Keys must match the resource names in src/CGMBootstrap.js.
   Segment titles are kept to three characters so five of them still fit the
   340pt panel width. */
static NSString * const kCGMResKeys[]  = { @"gem", @"coin", @"power", @"adcoupon", @"cloth" };
static NSString * const kCGMResNames[] = { @"钻石", @"金币", @"燃油", @"广告券", @"换装币" };
static const int kCGMResCount = 5;'''
assert old in s, "res table anchor missing"
s = s.replace(old, new, 1); n += 1

# --- segmented control: five items -------------------------------------------
old2 = 'self.resSeg = [[UISegmentedControl alloc] initWithItems:@[kCGMResNames[0], kCGMResNames[1], kCGMResNames[2], kCGMResNames[3]]];'
new2 = '''{
        NSMutableArray *titles = [NSMutableArray array];
        for (int i = 0; i < kCGMResCount; i++) { [titles addObject:kCGMResNames[i]]; }
        self.resSeg = [[UISegmentedControl alloc] initWithItems:titles];
        if (@available(iOS 13.0, *)) { self.resSeg.apportionsSegmentWidthsByContent = NO; }
        self.resSeg.titleTextAttributes = @{ NSFontAttributeName: [UIFont boldSystemFontOfSize:12.0] };
    }'''
assert old2 in s, "segmented anchor missing"
s = s.replace(old2, new2, 1); n += 1

# --- touch telemetry in the window -------------------------------------------
old3 = '''@implementation CGMWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {'''
new3 = '''@implementation CGMWindow
- (void)sendEvent:(UIEvent *)event {
    /* Any touch that makes it into this window is logged once, so a missing
       drag can be told apart from touches never arriving at all. */
    for (UITouch *t in event.allTouches) {
        if (t.phase == UITouchPhaseBegan) {
            CGMLog(@"window touch began at %.0f,%.0f (type=%ld)",
                   [t locationInView:self].x, [t locationInView:self].y, (long)t.type);
        }
    }
    [super sendEvent:event];
}

- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {'''
assert old3 in s, "window anchor missing"
s = s.replace(old3, new3, 1); n += 1

# --- hit test must not swallow touches aimed at children ---------------------
s = s.replace('''- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *v = [super hitTest:point withEvent:event];
    if (v == self || v == self.rootViewController.view) { return nil; }
    return v;
}''',
'''- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *v = [super hitTest:point withEvent:event];
    /* Return nil for the bare window/root so the game keeps receiving input
       everywhere the overlay has no control. */
    if (v == self || v == self.rootViewController.view) { return nil; }
    return v;
}''', 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ObjC patches:", n, "size:", len(s))
for k in ["kCGMResCount = 5", "换装币", "window touch began", "apportionsSegmentWidths"]:
    print(k, "->", s.count(k))
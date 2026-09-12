import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# --- cfg: rotation -----------------------------------------------------------
s = s.replace('static int gCfgPanelOpen = 0; /* open the panel at launch (layout diagnostics)   */',
              'static int gCfgPanelOpen = 0; /* open the panel at launch (layout diagnostics)   */\nstatic int gCfgRot = 90;      /* rotate the overlay to match the game\'s drawing  */', 1)
s = s.replace('    else if (strcmp(key, "panel") == 0) { gCfgPanelOpen = val; }',
              '    else if (strcmp(key, "panel") == 0) { gCfgPanelOpen = val; }\n    else if (strcmp(key, "rot") == 0) { gCfgRot = atoi(eq + 1); }', 1)
s = s.replace('CGMLog(@"config: objc=%d posix=%d overlay=%d panel=%d", gCfgObjc, gCfgPosix, gCfgOverlay, gCfgPanelOpen);',
              'CGMLog(@"config: objc=%d posix=%d overlay=%d panel=%d rot=%d", gCfgObjc, gCfgPosix, gCfgOverlay, gCfgPanelOpen, gCfgRot);', 1)
n += 3

# --- add a stage view --------------------------------------------------------
s = s.replace("@property (nonatomic, strong) UIButton *ball;",
              "@property (nonatomic, strong) UIView *stage;\n@property (nonatomic, strong) UIButton *ball;", 1)
n += 1

# build stage in viewDidLoad, and attach ball/panel to it
s = s.replace("""    self.view.backgroundColor = [UIColor clearColor];
    self.view.userInteractionEnabled = YES;
    [self buildBall];
    [self buildPanel];""",
"""    self.view.backgroundColor = [UIColor clearColor];
    self.view.userInteractionEnabled = YES;
    self.stage = [[UIView alloc] initWithFrame:CGRectZero];
    self.stage.backgroundColor = [UIColor clearColor];
    self.stage.autoresizingMask = UIViewAutoresizingNone;
    [self.view addSubview:self.stage];
    [self buildBall];
    [self buildPanel];""", 1)
n += 1

s = s.replace("    [self.view addSubview:self.ball];\n}", "    [self.stage addSubview:self.ball];\n}", 1)
s = s.replace("    [self.view addSubview:self.panel];\n}", "    [self.stage addSubview:self.panel];\n}", 1)
n += 2

# --- geometry: centred rotating stage ---------------------------------------
s = s.replace("""- (CGRect)safeFrame {
    CGRect b = self.view.bounds;
    if (@available(iOS 11.0, *)) {
        UIEdgeInsets in = self.view.safeAreaInsets;
        b.origin.x += in.left; b.origin.y += in.top;
        b.size.width -= (in.left + in.right);
        b.size.height -= (in.top + in.bottom);
    }
    return b;
}""",
"""/* The app declares landscape only, but the game rotates its own artwork, so a
   plain landscape overlay shows up sideways. `stage` is laid out in the game's
   visual orientation and then rotated to sit on top of the real window. */
- (CGRect)safeFrame {
    CGRect vb = self.view.bounds;
    BOOL rotated = (gCfgRot == 90 || gCfgRot == 270 || gCfgRot == -90 || gCfgRot == -270);
    CGRect b = rotated ? CGRectMake(0, 0, vb.size.height, vb.size.width) : vb;
    UIEdgeInsets in = UIEdgeInsetsZero;
    if (@available(iOS 11.0, *)) { in = self.view.safeAreaInsets; }
    if (rotated) {
        UIEdgeInsets sin = UIEdgeInsetsMake(in.left, in.bottom, in.right, in.top);
        in = sin;
    }
    b.origin.x += in.left; b.origin.y += in.top;
    b.size.width -= (in.left + in.right);
    b.size.height -= (in.top + in.bottom);
    return b;
}

- (void)layoutStage {
    CGRect vb = self.view.bounds;
    if (vb.size.width < 1 || vb.size.height < 1) { return; }
    CGFloat angle = (CGFloat)gCfgRot * (CGFloat)M_PI / 180.0;
    CGRect area = [self safeFrame];
    self.stage.transform = CGAffineTransformIdentity;
    self.stage.bounds = CGRectMake(0, 0, area.size.width, area.size.height);
    self.stage.center = CGPointMake(CGRectGetMidX(vb), CGRectGetMidY(vb));
    if (gCfgRot != 0) { self.stage.transform = CGAffineTransformMakeRotation(angle); }
}""", 1)
n += 1

# call layoutStage before laying out children, and report the stage rect
s = s.replace("""- (void)layoutChrome {
    CGRect safe = [self safeFrame];
    if (safe.size.width < 10 || safe.size.height < 10) { return; }""",
"""- (void)layoutChrome {
    [self layoutStage];
    CGRect safe = [self safeFrame];
    if (safe.size.width < 10 || safe.size.height < 10) { return; }""", 1)
n += 1

# ui_state: report stage
s = s.replace("""        @"view":  @{ @"w": @(vb.size.width),  @"h": @(vb.size.height) },""",
"""        @"view":  @{ @"w": @(vb.size.width),  @"h": @(vb.size.height) },
        @"stage": @{ @"w": @(self.stage.bounds.size.width), @"h": @(self.stage.bounds.size.height) },
        @"rot":   @(gCfgRot),""", 1)
n += 1

# keep the [hits] spam out of the visible log
s = s.replace("""                CGMLog(@"hook hits: %@", parts.count ? [parts componentsJoinedByString:@" "] : @"(none)");
                [gVC appendLog:[NSString stringWithFormat:@"[hits] %@",
                                parts.count ? [parts componentsJoinedByString:@" "] : @"(none)"]];""",
"""                CGMLog(@"hook hits: %@", parts.count ? [parts componentsJoinedByString:@" "] : @"(none)");""", 1)
n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["gCfgRot","self.stage","layoutStage","M_PI"]:
    print(k, s.count(k))
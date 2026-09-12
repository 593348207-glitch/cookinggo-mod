import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# --- cfg: add panel switch ---------------------------------------------------
s = s.replace(
 "static int gCfgOverlay = 1;   /* floating panel UI                               */",
 "static int gCfgOverlay = 1;   /* floating panel UI                               */\nstatic int gCfgPanelOpen = 0; /* open the panel at launch (layout diagnostics)   */", 1)
s = s.replace(
 '    else if (strcmp(key, "overlay") == 0) { gCfgOverlay = val; }',
 '    else if (strcmp(key, "overlay") == 0) { gCfgOverlay = val; }\n    else if (strcmp(key, "panel") == 0) { gCfgPanelOpen = val; }', 1)
s = s.replace('CGMLog(@"config: objc=%d posix=%d overlay=%d", gCfgObjc, gCfgPosix, gCfgOverlay);',
              'CGMLog(@"config: objc=%d posix=%d overlay=%d panel=%d", gCfgObjc, gCfgPosix, gCfgOverlay, gCfgPanelOpen);', 1)
n += 3

# --- VC: diagnostics label + logging + ui_state ------------------------------
s = s.replace(
"""- (void)togglePanel {
    self.panelVisible = !self.panelVisible;
    self.panel.hidden = !self.panelVisible;
    if (self.panelVisible) { [self refreshStatus]; } else { [self dismissKeyboard]; }
}""",
"""- (void)togglePanel {
    [self setPanelVisible:!self.panelVisible];
}

- (void)setPanelVisible:(BOOL)visible {
    self.panelVisible = visible;
    self.panel.hidden = !visible;
    CGMLog(@"panel %@ (view=%.0fx%.0f window=%.0fx%.0f ball=%.0f,%.0f)",
           visible ? @"OPENED" : @"closed", self.view.bounds.size.width, self.view.bounds.size.height,
           self.view.window.bounds.size.width, self.view.window.bounds.size.height,
           self.ball.center.x, self.ball.center.y);
    [self writeUIState];
    if (visible) { [self refreshStatus]; } else { [self dismissKeyboard]; }
}

- (void)writeUIState {
    if (!gMailboxPath) { return; }
    CGRect vb = self.view.bounds;
    CGRect wf = self.view.window ? self.view.window.frame : CGRectZero;
    NSDictionary *d = @{
        @"panelVisible": @(self.panelVisible),
        @"view":  @{ @"w": @(vb.size.width),  @"h": @(vb.size.height) },
        @"window": @{ @"x": @(wf.origin.x), @"y": @(wf.origin.y),
                      @"w": @(wf.size.width), @"h": @(wf.size.height) },
        @"ball":  @{ @"x": @(self.ball.frame.origin.x), @"y": @(self.ball.frame.origin.y),
                     @"w": @(self.ball.frame.size.width), @"h": @(self.ball.frame.size.height) },
        @"panel": @{ @"x": @(self.panel.frame.origin.x), @"y": @(self.panel.frame.origin.y),
                     @"w": @(self.panel.frame.size.width), @"h": @(self.panel.frame.size.height) },
        @"input": @{ @"x": @(self.input.frame.origin.x), @"y": @(self.input.frame.origin.y),
                     @"w": @(self.input.frame.size.width), @"h": @(self.input.frame.size.height) },
        @"ts": @((long long)[[NSDate date] timeIntervalSince1970])
    };
    CGMWriteJSON(d, [gMailboxPath stringByAppendingPathComponent:@"ui_state.json"]);
}""", 1)
n += 1

# call writeUIState from layout
s = s.replace("""    CGFloat logH = panelH - y - pad;
    if (logH < 60.0) { logH = 60.0; }
    self.logView.frame = CGRectMake(pad, y, panelW - 2.0 * pad, logH);
}""",
"""    CGFloat logH = panelH - y - pad;
    if (logH < 60.0) { logH = 60.0; }
    self.logView.frame = CGRectMake(pad, y, panelW - 2.0 * pad, logH);
    [self writeUIState];
}""", 1)

# --- tick: honour ui_cmd.json ------------------------------------------------
s = s.replace("""        if (hello && !gEngineReady) {""",
"""        NSDictionary *uiCmd = CGMReadJSON([gChosenMailbox stringByAppendingPathComponent:@"ui_cmd.json"]);
        if (uiCmd) {
            static NSInteger lastUiSeq = -1;
            NSInteger useq = [uiCmd[@"seq"] integerValue];
            if (useq != lastUiSeq) {
                lastUiSeq = useq;
                if (uiCmd[@"panel"] != nil) {
                    BOOL want = [uiCmd[@"panel"] boolValue];
                    if (gVC.panelVisible != want) { [gVC setPanelVisible:want]; }
                }
                if ([uiCmd[@"log"] isKindOfClass:[NSString class]]) {
                    [gVC appendLog:uiCmd[@"log"]];
                }
            }
        }

        if (hello && !gEngineReady) {""", 1)
n += 1

# --- launch: honour panel=1 --------------------------------------------------
s = s.replace("""        CGMSetupWindow();
        CGMStartTick();
    });""",
"""        CGMSetupWindow();
        CGMStartTick();
        if (gCfgPanelOpen && gVC) { [gVC setPanelVisible:YES]; }
    });""", 1)
n += 1

# --- declare the new VC methods in the interface -----------------------------
s = s.replace("@property (nonatomic, assign) BOOL didInitPositions;\n- (void)appendLog:(NSString *)line;",
              "@property (nonatomic, assign) BOOL didInitPositions;\n- (void)appendLog:(NSString *)line;\n- (void)setPanelVisible:(BOOL)visible;\n- (void)writeUIState;", 1)
n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
for k in ["gCfgPanelOpen","setPanelVisible","writeUIState","ui_cmd.json","ui_state.json"]:
    print(k, s.count(k))
import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
n = 0

# 1. no rotation by default ----------------------------------------------------
s = s.replace("static int gCfgRot = 90;", "static int gCfgRot = 0;", 1); n += 1

# 2. hide the status line under 自检 ------------------------------------------
old = '''    self.statusLabel = [self makeLabel:@"JS: 等待注入..." size:11.0 bold:NO color:[UIColor colorWithWhite:0.85 alpha:1.0]];
    [self.panel addSubview:self.statusLabel];'''
new = '''    /* Deliberately NOT added to the panel: the status line under 自检 is hidden.
       Live state is still available in mod.log and ui_state.json. */
    self.statusLabel = [self makeLabel:@"" size:11.0 bold:NO color:[UIColor colorWithWhite:0.85 alpha:1.0]];'''
assert old in s, "status label anchor missing"
s = s.replace(old, new, 1); n += 1

# 3. keep the 自检 row compact without the label ------------------------------
old2 = '''    self.probeButton.frame = CGRectMake(pad, y, 60.0, 24.0);
    self.statusLabel.frame = CGRectMake(pad + 68.0, y, panelW - 3.0 * pad - 68.0, 24.0);
    y += 24.0 + 8.0;'''
new2 = '''    self.probeButton.frame = CGRectMake(pad, y, 60.0, 24.0);
    y += 24.0 + 8.0;'''
assert old2 in s, "probe row anchor missing"
s = s.replace(old2, new2, 1); n += 1

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patches:", n, "size:", len(s))
print("gCfgRot default 0 ->", "static int gCfgRot = 0;" in s)
print("statusLabel addSubview ->", s.count("[self.panel addSubview:self.statusLabel]"))
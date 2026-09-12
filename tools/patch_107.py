import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
old = """- (void)setPanelVisible:(BOOL)visible {
    self.panelVisible = visible;
    self.panel.hidden = !visible;"""
new = """/* NOTE: `panelVisible` is a property, so `self.panelVisible = x` inside this
   custom setter would call this very method again and recurse until the stack
   blows (that is exactly what killed 1.0.6). Write the backing ivar instead. */
- (void)setPanelVisible:(BOOL)visible {
    _panelVisible = visible;
    self.panel.hidden = !visible;"""
assert old in s, "setter not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("fixed recursion, size", len(s))
# sanity: no other self.<prop> = inside its own setter
import re
bad = re.findall(r"- \(void\)set([A-Z]\w+):[^}]*?self\.\1\s*=", s, re.S)
print("remaining self-assign recursion patterns:", bad)
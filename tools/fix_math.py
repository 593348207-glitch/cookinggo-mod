import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
if "#import <math.h>" not in s:
    s = s.replace("#import <stdarg.h>", "#import <stdarg.h>\n#import <math.h>", 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("math.h ok:", "#import <math.h>" in s)
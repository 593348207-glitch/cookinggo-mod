import io
P = r"F:\测试\cookingGO\mod\src\CookingGoMod.m"
s = io.open(P, encoding="utf-8").read()
s = s.replace("""    self.ball.center = c;
    self.ballCenter = c;
    [self writeUIState];
}

- (void)persistBallPosition {""",
"""    self.ball.center = c;
    self.ballCenter = c;
}

- (void)persistBallPosition {""", 1)
s = s.replace("""    if (self.ballDragMoved) {
        CGMLog(@"drag end -> ball=%.0f,%.0f", b.center.x, b.center.y);
        [self persistBallPosition];
    }""",
"""    if (self.ballDragMoved) {
        CGMLog(@"drag end -> ball=%.0f,%.0f", b.center.x, b.center.y);
        [self persistBallPosition];
        [self writeUIState];
    }""", 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("write spam removed; size", len(s))
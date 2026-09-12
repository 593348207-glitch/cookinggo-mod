import io
P = r"F:\测试\cookingGO\mod\tools\verify_deb.sh"
s = io.open(P, encoding="utf-8").read()
old = """echo "== required payload (control archive)"
if dpkg-deb --ctrl-tarfile "$DEB" | tar -t 2>/dev/null | grep -q './control'; then
  echo "   ok ./control"
else
  echo "!! control archive missing ./control"; fail=1
fi
"""
new = """echo "== required payload (control archive)"
CTRL_LIST="$(dpkg-deb --ctrl-tarfile "$DEB" 2>/dev/null | tar -t 2>/dev/null || true)"
for cfile in ./control ./postinst ./postrm; do
  if printf '%s\\n' "$CTRL_LIST" | grep -qx "$cfile"; then
    echo "   ok $cfile"
  else
    echo "!! control archive missing $cfile"; fail=1
  fi
done
"""
assert old in s, "ctrl block not found"
s = s.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("verify script updated")
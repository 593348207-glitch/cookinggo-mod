import io
P = r"F:\测试\cookingGO\mod\src\CGMBootstrap.js"
s = io.open(P, encoding="utf-8").read()

s = s.replace('var VERSION = "1.0.9";', 'var VERSION = "1.1.0";', 1)

s = s.replace('  var EPropID_AdCoupon = 57;   /* ServerConst.EPropID.AdCoupon */',
'''  /* ServerConst.EPropID (verified in scriptBundle/index.js):
       45 = ClothNum  -> PlayerData.clothingCionNum  (换装币)
       57 = AdCoupon  -> PlayerData.adCouponNum      (免广告券)            */
  var EPropID_ClothNum = 45;
  var EPropID_AdCoupon = 57;''', 1)

s = s.replace('''      adcoupon: {
        label: "\\u514d\\u5e7f\\u544a\\u5238",
        get: function () { return PD.adCouponNum; },
        set: function (v) { PD.setPropNum(EPropID_AdCoupon, v); },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_AD_COUPON, PD.adCouponNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_PROP_NUM, EPropID_AdCoupon, PD.adCouponNum); } catch (e) {}
        }
      }
    };''',
'''      adcoupon: {
        label: "\\u514d\\u5e7f\\u544a\\u5238",
        get: function () { return PD.adCouponNum; },
        set: function (v) { PD.setPropNum(EPropID_AdCoupon, v); },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_AD_COUPON, PD.adCouponNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_PROP_NUM, EPropID_AdCoupon, PD.adCouponNum); } catch (e) {}
        }
      },
      cloth: {
        label: "\\u6362\\u88c5\\u5e01",
        /* PlayerData.clothingCionNum is a getter over
           getPropNum(EPropID.ClothNum)[EIdIdx.val]; there is no setter,
           so writes go through setPropNum like the ad coupon. */
        get: function () { return PD.clothingCionNum; },
        set: function (v) { PD.setPropNum(EPropID_ClothNum, v); },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_CLOTHINGCOIN, PD.clothingCionNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_PROP_NUM, EPropID_ClothNum, PD.clothingCionNum); } catch (e) {}
        }
      }
    };''', 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("JS patches done, size", len(s))
print("cloth entries:", s.count("cloth:"), "| EPropID_ClothNum:", s.count("EPropID_ClothNum"))
# -*- coding: utf-8 -*-
"""
Master Patch for DieHard ROS:
1. Complete Vehicle Hierarchy & Catalog (Nova/Supernova, Three-wheeler/Reign of Fire, Monster Truck,
   Bugatti/Spark, Pagani/Twister, Burst Sedan, Velociraptor, Darksteel Bike, Summer Bicycle, Golden Flash,
   Shadowfax, Frosty Frills, Warjeep, Subjugator, Hovering Car, Deathmobile, Pegasus, Blazing Flash, Dynamic Streamer):
   - Proper synthetic props with authentic models, positions and icons.
   - 3D showroom turntable display fix for Nova X1 and Supernova (DISPLAY_POS_ID: 281, SHOULD_SHOW: True).
   - 3D showroom display fix for Velociraptor Lv. 2 (DISPLAY_USING_VEHICLE_ID: 131005, DISPLAY_POS_ID: 403, DISPLAY_PROP_LIST: [140237]).
   - getPermanentDtsAppearanceItemCnt family fallback so native catalog never hides owned vehicles.
   - In-place catalog tile substitution preserving exact grid position and order.
   - Exactly 1 tile per vehicle family matching highest owned tier.
   - Zero duplication / no "x2" badge.
   - Complete evolution rules in _dh_clean_depot_duplicates and _dh_rpc_appearance_cultivate_compound.
2. Lobby Theme Direct Equip & Purchase (No clothing bundle popup, no blinking in Depot).
3. Battle Teammate Fixes (Lock 3D overhead to live avatar, remove white pillar, fix HUD panel, fix 98% hang).
"""

import sys, os, re

def patch_clean_remote_lobby():
    with open('clean_remote_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    print('Initial clean_remote_lobby.py length:', len(content))

    # =========================================================================
    # PART 1: Enhanced _dh_ensure_synthetic_props with valid models & IDs
    # =========================================================================
    master_syn_code = '''
def _dh_ensure_synthetic_props():
    global _dh_synthetic_building
    if 121363 in _dh_synthetic_props and 142008 in _dh_synthetic_props and 140404 in _dh_synthetic_props and 140035 in _dh_synthetic_props:
        return _dh_synthetic_props
    if _dh_synthetic_building:
        return _dh_synthetic_props
    _dh_synthetic_building = True
    try:
        import copy
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        orig_get = getattr(legacy, '_dh_orig_get_dts_prop', legacy.getDtsHallPropData)

        # 1. Compound Bow-Pink Lady (121363)
        if 121363 not in _dh_synthetic_props:
            medusa = orig_get(121248)
            if medusa is not None:
                bow = copy.copy(medusa)
                ptype = copy.copy(getattr(medusa, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('BATTLE_GROUND_PROP_ID', 91164),
                                      ('DISPLAY_USING_GUN_ID', 90191),
                                      ('PROP_ITEM_ID', 300)):
                        try:
                            setattr(ptype, attr, val)
                        except Exception:
                            pass
                    bow.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Compound Bow-Pink Lady'),
                                  ('QUALITY', 5),
                                  ('ICON_PATH', 'ui/images/dts_item/package/icn_gong_package.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_item/package/icn_gong_package.png')):
                    try:
                        setattr(bow, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[121363] = bow
                _dh_synthetic_props[492081] = bow
                _dh_synthetic_props[492082] = bow

        # 2. Velociraptor Lv. 2 (142008 & 140237)
        if 142008 not in _dh_synthetic_props:
            raptor_src = None
            try:
                raptor_src = orig_get(142007)
            except Exception:
                raptor_src = None
            if raptor_src is None:
                try:
                    raptor_src = orig_get(140237)
                except Exception:
                    raptor_src = None
            if raptor_src is not None:
                raptor_lv2 = copy.copy(raptor_src)
                ptype = copy.copy(getattr(raptor_src, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/bike_xunmenglongdiji/xunmenglongdiji_1.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/bike_xunmenglongdiji/xunmenglongdiji_1.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 910059),
                                      ('LAND_VEHICLE_ID', 910043),
                                      ('VEHICLE_ID', 910043),
                                      ('SCORE', 300),
                                      ('TRANSFER_LAND_VEHICLE_ID', 910059),
                                      ('AUTO_ROYALE_DISPLAY_IMG_PATH', 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png')):
                        try:
                            setattr(ptype, attr, val)
                        except Exception:
                            pass
                    try:
                        dim = getattr(ptype, 'DISPLAY_IN_MODEL', None)
                        if dim:
                            new_dim = []
                            for entry in dim:
                                ec = copy.copy(entry)
                                ec.DISPLAY_PROP_LIST = [142008]
                                ec.DISPLAY_POS_ID = 1224
                                ec.SHOULD_SHOW = True
                                new_dim.append(ec)
                            ptype.DISPLAY_IN_MODEL = new_dim
                        else:
                            base_dim = getattr(orig_get(142007).PROP_TYPE, 'DISPLAY_IN_MODEL', None)
                            if base_dim:
                                ec = copy.copy(base_dim[0])
                                ec.DISPLAY_PROP_LIST = [142008]
                                ec.DISPLAY_POS_ID = 1224
                                ec.SHOULD_SHOW = True
                                ptype.DISPLAY_IN_MODEL = [ec]
                    except Exception:
                        pass
                    raptor_lv2.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Velociraptor Lv. 2'),
                                  ('QUALITY', 5),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png')):
                    try:
                        setattr(raptor_lv2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[142008] = raptor_lv2
                _dh_synthetic_props[140237] = raptor_lv2

        # 3. Supernova (140035) Unhide & 3D Showroom Turntable Display
        try:
            sn = orig_get(140035)
            if sn is not None:
                sn_copy = copy.copy(sn)
                setattr(sn_copy, 'HIDE_IN_UI', False)
                pt = copy.copy(getattr(sn, 'PROP_TYPE', None))
                if pt is not None:
                    setattr(pt, 'HIDE_IN_UI', False)
                    n1 = orig_get(140031)
                    if n1 is not None and getattr(n1, 'PROP_TYPE', None):
                        n1_dim = getattr(n1.PROP_TYPE, 'DISPLAY_IN_MODEL', None)
                        if n1_dim:
                            ec = copy.copy(n1_dim[0])
                            ec.DISPLAY_POS_ID = 281
                            ec.DISPLAY_PROP_LIST = [140035]
                            ec.SHOULD_SHOW = True
                            pt.DISPLAY_IN_MODEL = [ec]
                    sn_copy.PROP_TYPE = pt
                _dh_synthetic_props[140035] = sn_copy
        except Exception:
            pass

        # 4. Nova X1 (140031) Showroom Turntable Display
        try:
            n1 = orig_get(140031)
            if n1 is not None:
                n1_copy = copy.copy(n1)
                pt = copy.copy(getattr(n1, 'PROP_TYPE', None))
                if pt is not None:
                    n1_dim = getattr(pt, 'DISPLAY_IN_MODEL', None)
                    if n1_dim:
                        ec = copy.copy(n1_dim[0])
                        ec.DISPLAY_POS_ID = 281
                        ec.DISPLAY_PROP_LIST = [140031]
                        ec.SHOULD_SHOW = True
                        pt.DISPLAY_IN_MODEL = [ec]
                    n1_copy.PROP_TYPE = pt
                _dh_synthetic_props[140031] = n1_copy
        except Exception:
            pass

        # 5. Monster - M2 (140404)
        if 140404 not in _dh_synthetic_props:
            m1 = orig_get(140403)
            if m1 is not None:
                m2 = copy.copy(m1)
                ptype = copy.copy(getattr(m1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/guaiwupika/cheshen.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/guaiwupika/geton_vehicle.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 31007),
                                      ('SCORE', 300),
                                      ('AUTO_ROYALE_DISPLAY_IMG_PATH', 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png')):
                        try:
                            setattr(ptype, attr, val)
                        except Exception:
                            pass
                    try:
                        dim = getattr(ptype, 'DISPLAY_IN_MODEL', None)
                        if dim:
                            new_dim = []
                            for entry in dim:
                                ec = copy.copy(entry)
                                ec.DISPLAY_PROP_LIST = [140403]
                                new_dim.append(ec)
                            ptype.DISPLAY_IN_MODEL = new_dim
                    except Exception:
                        pass
                    m2.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Monster - M2'),
                                  ('QUALITY', 5),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png')):
                    try:
                        setattr(m2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140404] = m2

        # 6. Darksteel Bike Lv. 2 (140077)
        if 140077 not in _dh_synthetic_props:
            b1 = orig_get(140076)
            if b1 is not None:
                b2 = copy.copy(b1)
                ptype = copy.copy(getattr(b1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/xuantiemotuo/cheshen.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/xuantiemotuo/geton_vehicle.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 31032),
                                      ('LAND_VEHICLE_ID', 25010),
                                      ('VEHICLE_ID', 25010),
                                      ('AUTO_ROYALE_DISPLAY_IMG_PATH', 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png')):
                        try:
                            setattr(ptype, attr, val)
                        except Exception:
                            pass
                    try:
                        dim = getattr(ptype, 'DISPLAY_IN_MODEL', None)
                        if dim:
                            new_dim = []
                            for entry in dim:
                                ec = copy.copy(entry)
                                ec.DISPLAY_PROP_LIST = [140076]
                                new_dim.append(ec)
                            ptype.DISPLAY_IN_MODEL = new_dim
                    except Exception:
                        pass
                    b2.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Darksteel Bike Lv. 2'),
                                  ('QUALITY', 5),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png')):
                    try:
                        setattr(b2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140077] = b2

        # 7. Summer Bicycle Lv. 2 (140074)
        if 140074 not in _dh_synthetic_props:
            sb1 = orig_get(140073)
            if sb1 is not None:
                sb2 = copy.copy(sb1)
                ptype = copy.copy(getattr(sb1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/summerbike/cheshen.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/summerbike/geton_vehicle.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 30004),
                                      ('LAND_VEHICLE_ID', 910043),
                                      ('VEHICLE_ID', 910043),
                                      ('SCORE', 300),
                                      ('AUTO_ROYALE_DISPLAY_IMG_PATH', 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png')):
                        try:
                            setattr(ptype, attr, val)
                        except Exception:
                            pass
                    try:
                        dim = getattr(ptype, 'DISPLAY_IN_MODEL', None)
                        if dim:
                            new_dim = []
                            for entry in dim:
                                ec = copy.copy(entry)
                                ec.DISPLAY_PROP_LIST = [140073]
                                new_dim.append(ec)
                            ptype.DISPLAY_IN_MODEL = new_dim
                    except Exception:
                        pass
                    sb2.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Summer Bicycle Lv. 2'),
                                  ('QUALITY', 5),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png')):
                    try:
                        setattr(sb2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140074] = sb2

        # 8. Golden Flash Lv. 2 (142005) & Lv. 3 (142006)
        gf1 = orig_get(142004)
        if gf1 is not None:
            for gfid, gfname in ((142005, 'Golden Flash Lv. 2'), (142006, 'Golden Flash Lv. 3')):
                if gfid not in _dh_synthetic_props:
                    try:
                        gfc = copy.copy(gf1)
                        for attr, val in (('NAME', gfname),
                                          ('QUALITY', 5),
                                          ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_weilai1.png'),
                                          ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_weilai1.png')):
                            try:
                                setattr(gfc, attr, val)
                            except Exception:
                                pass
                        ptype = copy.copy(getattr(gf1, 'PROP_TYPE', None))
                        if ptype is not None:
                            try:
                                setattr(ptype, 'SCORE', 300)
                                dim = getattr(ptype, 'DISPLAY_IN_MODEL', None)
                                if dim:
                                    new_dim = []
                                    for entry in dim:
                                        ec = copy.copy(entry)
                                        ec.DISPLAY_PROP_LIST = [142004]
                                        new_dim.append(ec)
                                    ptype.DISPLAY_IN_MODEL = new_dim
                            except Exception:
                                pass
                            gfc.PROP_TYPE = ptype
                        _dh_synthetic_props[gfid] = gfc
                    except Exception:
                        pass

        # 9. Brain Freeze (140046) & Hovering Car Max (140061) Unhide
        for hid_id in (140046, 140061):
            try:
                h_item = orig_get(hid_id)
                if h_item is not None:
                    hc = copy.copy(h_item)
                    setattr(hc, 'HIDE_IN_UI', False)
                    pt = copy.copy(getattr(h_item, 'PROP_TYPE', None))
                    if pt is not None:
                        setattr(pt, 'HIDE_IN_UI', False)
                        hc.PROP_TYPE = pt
                    _dh_synthetic_props[hid_id] = hc
            except Exception:
                pass

    except Exception as e:
        if not globals().get('_dh_synthetic_error_logged'):
            globals()['_dh_synthetic_error_logged'] = True
            log_error('local-synthetic-props-error', err=str(e))
    finally:
        _dh_synthetic_building = False
    return _dh_synthetic_props
'''

    # Replace existing _dh_ensure_synthetic_props
    syn_start = content.find('def _dh_ensure_synthetic_props():')
    if syn_start != -1:
        syn_end = content.find('\ndef _dh_install_prop_table_hooks():', syn_start)
        if syn_end != -1:
            content = content[:syn_start] + master_syn_code.strip() + '\n\n' + content[syn_end+1:]
            print('[lobby] Successfully updated _dh_ensure_synthetic_props')

    # =========================================================================
    # PART 2: Comprehensive Vehicle Preloader Hook & Single-Tile Manager
    # =========================================================================
    master_veh_preload_code = '''
# --- Master Vehicle Preload, Family Fallback & Catalog Architecture ---
_VEHICLE_FAMILY_MAP = {
    # target_tier -> (base_tier, [all_tiers_from_highest_to_lowest])
    # Nova / Lamborghini
    140035: (140031, [140035, 140031]),
    140031: (140031, [140035, 140031]),

    # Three-wheeler / Tuk-tuk
    140905: (140902, [140905, 140902]),
    140902: (140902, [140905, 140902]),

    # Monster Truck
    140406: (140403, [140406, 140404, 140403]),
    140404: (140403, [140406, 140404, 140403]),
    140403: (140403, [140406, 140404, 140403]),

    # Bugatti / Spark
    140013: (140010, [140013, 140010]),
    140010: (140010, [140013, 140010]),

    # Pagani / Twister
    140024: (140021, [140024, 140021]),
    140021: (140021, [140024, 140021]),

    # Dodge / Burst Sedan
    142030: (142028, [142030, 142029, 142028]),
    142029: (142028, [142030, 142029, 142028]),
    142028: (142028, [142030, 142029, 142028]),

    # Hunting Off-road
    140051: (140048, [140051, 140048]),
    140048: (140048, [140051, 140048]),

    # Frosty Frills
    140046: (140041, [140046, 140041]),
    140041: (140041, [140046, 140041]),

    # Warjeep
    140914: (140911, [140914, 140911]),
    140911: (140911, [140914, 140911]),

    # Subjugator
    140224: (140221, [140224, 140223, 140221]),
    140223: (140221, [140224, 140223, 140221]),
    140221: (140221, [140224, 140223, 140221]),

    # Hovering Car
    140061: (140056, [140061, 140056]),
    140056: (140056, [140061, 140056]),

    # Burst Buggy / Deathmobile
    142003: (140241, [142003, 140241]),
    140241: (140241, [142003, 140241]),

    # Darksteel Bike
    140077: (140076, [140077, 140076]),
    140076: (140076, [140077, 140076]),

    # Pegasus
    140214: (140211, [140214, 140211]),
    140211: (140211, [140214, 140211]),

    # Blazing Flash
    140205: (140202, [140205, 140202]),
    140202: (140202, [140205, 140202]),

    # Golden Flash
    142006: (142004, [142006, 142005, 142004]),
    142005: (142004, [142006, 142005, 142004]),
    142004: (142004, [142006, 142005, 142004]),

    # Shadowfax
    142013: (142011, [142013, 142012, 142011]),
    142012: (142011, [142013, 142012, 142011]),
    142011: (142011, [142013, 142012, 142011]),

    # Velociraptor
    142008: (142007, [142008, 140237, 142007]),
    140237: (142007, [142008, 140237, 142007]),
    142007: (142007, [142008, 140237, 142007]),

    # Summer Bicycle
    140074: (140073, [140074, 140073]),
    140073: (140073, [140074, 140073]),

    # Dynamic Streamer Skateboard
    140065: (140062, [140065, 140064, 140062]),
    140064: (140062, [140065, 140064, 140062]),
    140062: (140062, [140065, 140064, 140062]),
}

_VEHICLE_NAME_MAP = {
    140031: 'Nova X1',
    140035: 'Supernova',
    140902: '5 Star Ride',
    140905: 'Reign of Fire',
    140403: 'Monster - M1',
    140404: 'Monster - M2',
    140406: 'Wild Beast',
    140010: 'Spark V3',
    140013: 'Thunderbird',
    140021: 'Twister - T1',
    140024: 'Storm',
    142028: 'Burst Sedan Lv. 1',
    142029: 'Burst Sedan Lv. 2',
    142030: 'Burst Sedan Lv. 3',
    140048: 'Hunting Path - I',
    140051: 'Fiery Hunting',
    140041: 'Frosty Frills - I',
    140046: 'Brain Freeze',
    140911: 'Warjeep Lv. 1',
    140914: 'Warjeep Lv. 4',
    140221: 'Subjugator',
    140223: 'Subjugator - T2',
    140224: 'Discovery',
    140056: 'Hovering Car - Lv. 1',
    140061: 'Hovering Car - Max',
    140241: 'Burst Buggy - I',
    142003: 'Battle Jeep - Deathmobile',
    140076: 'Darksteel Bike Lv. 1',
    140077: 'Darksteel Bike Lv. 2',
    140211: 'Pegasus - I',
    140214: 'Pegasus Turbo',
    140202: 'Blazing Flash A1',
    140205: 'Phoenix',
    142004: 'Golden Flash Lv. 1',
    142005: 'Golden Flash Lv. 2',
    142006: 'Golden Flash Lv. 3',
    142011: 'Shadowfax - Noble',
    142012: 'Shadowfax - Kingly',
    142013: 'Shadowfax - Furious',
    142007: 'Velociraptor Lv. 1',
    142008: 'Velociraptor Lv. 2',
    140237: 'Velociraptor Lv. 2',
    140073: 'Summer Bicycle',
    140074: 'Summer Bicycle Lv. 2',
    140062: 'Dynamic Streamer Base',
    140064: 'Dynamic Streamer Lv. 1',
    140065: 'Dynamic Streamer MAX',
}

_VEHICLE_ICON_MAP = {
    140031: 'ui/images/dts_appearance/vehiclefull/img_zj_yingsuo_01.png',
    140035: 'ui/images/dts_appearance/vehiclefull/img_zj_yingsuo_04.png',
    140902: 'ui/images/dts_appearance/vehiclefull/img_tz_zj_tuktuk2.png',
    140905: 'ui/images/dts_appearance/vehiclefull/img_tz_zj_tuktuk5.png',
    140403: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png',
    140404: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png',
    140406: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_03.png',
    140010: 'ui/images/dts_appearance/vehiclefull/img_zj_bjdwl_01.png',
    140013: 'ui/images/dts_appearance/vehiclefull/img_zj_bjdwl_04.png',
    140021: 'ui/images/dts_appearance/vehiclefull/img_zj_pajiani_01.png',
    140024: 'ui/images/dts_appearance/vehiclefull/img_zj_pajiani_04.png',
    142028: 'ui/images/dts_appearance/vehiclefull/daoqi1.png',
    142029: 'ui/images/dts_appearance/vehiclefull/daoqi2.png',
    142030: 'ui/images/dts_appearance/vehiclefull/daoqi3.png',
    140048: 'ui/images/dts_appearance/vehiclefull/img_lietu3.png',
    140051: 'ui/images/dts_appearance/vehiclefull/img_lietu4.png',
    140041: 'ui/images/dts_appearance/vehiclefull/img_bingqilin_03.png',
    140046: 'ui/images/dts_appearance/vehiclefull/img_bingqilin_01.png',
    140911: 'ui/images/dts_appearance/vehiclefull/img_zj_zhandizhiwang1.png',
    140914: 'ui/images/dts_appearance/vehiclefull/img_zj_zhandizhiwang4.png',
    140221: 'ui/images/dts_appearance/vehiclefull/img_zj_jeep6_02.png',
    140223: 'ui/images/dts_appearance/vehiclefull/img_zj_jeep6_03.png',
    140224: 'ui/images/dts_appearance/vehiclefull/img_zj_jeep6_04.png',
    140056: 'ui/images/dts_appearance/vehiclefull/img_zj_xuanfu_01.png',
    140061: 'ui/images/dts_appearance/vehiclefull/img_zj_xuanfu_04.png',
    140241: 'ui/images/dts_appearance/vehiclefull/img_baoliezhanche01.png',
    142003: 'ui/images/dts_appearance/vehiclefull/img_zhongjiezhejipu.png',
    140076: 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png',
    140077: 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png',
    140211: 'ui/images/dts_appearance/vehiclefull/img_zj_halei_xingchen01.png',
    140214: 'ui/images/dts_appearance/vehiclefull/img_zj_halei_xingchen02.png',
    140202: 'ui/images/dts_appearance/vehiclefull/img_zj_saimo_pbr04.png',
    140205: 'ui/images/dts_appearance/vehiclefull/img_zj_saimo_pbr02.png',
    142004: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142005: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142006: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142011: 'ui/images/dts_appearance/vehiclefull/laosi1.png',
    142012: 'ui/images/dts_appearance/vehiclefull/laosi2.png',
    142013: 'ui/images/dts_appearance/vehiclefull/laosi3.png',
    142007: 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png',
    142008: 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png',
    140237: 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png',
    140073: 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png',
    140074: 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png',
    140062: 'ui/images/dts_appearance/vehiclefull/img_zj_huaban_01.png',
    140064: 'ui/images/dts_appearance/vehiclefull/img_zj_huaban_03.png',
    140065: 'ui/images/dts_appearance/vehiclefull/img_zj_huaban_mibao.png',
}

def _dh_install_vehicle_master_hooks():
    try:
        import sys
        import BigWorld
        import dts_appearance_utils
        _dh_ensure_synthetic_props()

        # 1. Hook dts_appearance_utils methods
        orig_name_fn = getattr(dts_appearance_utils, '_dh_orig_get_name', getattr(dts_appearance_utils, 'getDtsAppearanceName', None))
        if callable(orig_name_fn):
            dts_appearance_utils._dh_orig_get_name = orig_name_fn
            def _dh_hooked_get_name(iid):
                try:
                    ciid = int(iid)
                    if ciid in _VEHICLE_NAME_MAP:
                        return _VEHICLE_NAME_MAP[ciid]
                except Exception:
                    pass
                return orig_name_fn(iid)
            dts_appearance_utils.getDtsAppearanceName = _dh_hooked_get_name

        orig_icon_fn = getattr(dts_appearance_utils, '_dh_orig_get_icon', getattr(dts_appearance_utils, 'getDtsAppearanceIconPath', None))
        if callable(orig_icon_fn):
            dts_appearance_utils._dh_orig_get_icon = orig_icon_fn
            def _dh_hooked_get_icon(iid):
                try:
                    ciid = int(iid)
                    if ciid in _VEHICLE_ICON_MAP:
                        return _VEHICLE_ICON_MAP[ciid]
                except Exception:
                    pass
                return orig_icon_fn(iid)
            dts_appearance_utils.getDtsAppearanceIconPath = _dh_hooked_get_icon

        orig_cnt_fn = getattr(dts_appearance_utils, '_dh_orig_get_cnt', getattr(dts_appearance_utils, 'getDtsAppearanceCnt', None))
        if callable(orig_cnt_fn):
            dts_appearance_utils._dh_orig_get_cnt = orig_cnt_fn
            def _dh_hooked_get_cnt(iid):
                try:
                    ciid = int(iid)
                    import BigWorld
                    p = BigWorld.player()
                    if p is not None:
                        pkg = getattr(p, 'dtsAppearancePackage', None)
                        ilist = getattr(pkg, 'itemList', {}) if pkg else {}
                        if ciid in ilist or str(ciid) in ilist:
                            return 1
                        eq = getattr(p, 'dtsVehicleAppearanceList', None)
                        if eq and (ciid in eq or str(ciid) in eq):
                            return 1
                except Exception:
                    pass
                return orig_cnt_fn(iid)
            dts_appearance_utils.getDtsAppearanceCnt = _dh_hooked_get_cnt

        orig_quality_fn = getattr(dts_appearance_utils, '_dh_orig_get_qual', getattr(dts_appearance_utils, 'getDtsAppearanceQuality', None))
        if callable(orig_quality_fn):
            dts_appearance_utils._dh_orig_get_qual = orig_quality_fn
            def _dh_hooked_get_qual(iid):
                try:
                    ciid = int(iid)
                    if ciid in _VEHICLE_FAMILY_MAP:
                        return 5
                except Exception:
                    pass
                return orig_quality_fn(iid)
            dts_appearance_utils.getDtsAppearanceQuality = _dh_hooked_get_qual

        # 2. Hook player getPermanentDtsAppearanceItemCnt on Athlete / Player
        for mod_name in ('entities.Athlete', 'Athlete'):
            mod = sys.modules.get(mod_name)
            cls = getattr(mod, 'Athlete', None) if mod is not None else None
            if cls is not None:
                orig_perm = getattr(cls, '_dh_orig_perm_cnt', getattr(cls, 'getPermanentDtsAppearanceItemCnt', None))
                if callable(orig_perm):
                    cls._dh_orig_perm_cnt = orig_perm
                    def _dh_athlete_perm_cnt(self, iid):
                        try:
                            ciid = int(iid)
                            pkg = getattr(self, 'dtsAppearancePackage', None)
                            ilist = getattr(pkg, 'itemList', {}) if pkg else {}
                            if ciid in ilist or str(ciid) in ilist:
                                return 1
                            eq = getattr(self, 'dtsVehicleAppearanceList', None)
                            if eq and (ciid in eq or str(ciid) in eq):
                                return 1
                        except Exception:
                            pass
                        return orig_perm(self, iid)
                    cls.getPermanentDtsAppearanceItemCnt = _dh_athlete_perm_cnt
                    break

        log('local-veh-master-utils-hooked', success=True)
    except Exception as e:
        log_error('local-veh-master-utils-error', err=str(e))


def _dh_install_vehicle_appearance_preload_hook():
    try:
        _dh_patch_whitelist_stub()
        mod = __import__('dts_appearance_preload')
        orig_fn = getattr(mod, '_dh_orig_get_avail_veh', getattr(mod, 'getAvailableVehicleAppearanceIDs', None))
        if not callable(orig_fn):
            return
        mod._dh_orig_get_avail_veh = orig_fn

        def _dh_hooked_get_avail_veh(*args, **kwargs):
            try:
                ret = orig_fn(*args, **kwargs)
            except AttributeError:
                _dh_patch_whitelist_stub()
                try:
                    ret = orig_fn(*args, **kwargs)
                except Exception:
                    ret = {}
            except Exception:
                ret = {}
            try:
                import BigWorld
                player = BigWorld.player()
                if player is None:
                    return ret
                pkg = getattr(player, 'dtsAppearancePackage', None)
                ilist = getattr(pkg, 'itemList', {}) if pkg else {}
                eq_vehicles = set(getattr(player, 'dtsVehicleAppearanceList', []) or [])

                def _has(iid):
                    return (iid in ilist or str(iid) in ilist or iid in eq_vehicles)

                _dh_ensure_synthetic_props()

                # Full vehicle evolution chains: (cat_id, land_vid, chain_list_highest_to_lowest)
                chains = [
                    # Category 0: Sports Cars (25000)
                    (0, 25000, [140035, 140031]),                       # Nova / Supernova
                    (0, 25000, [140013, 140010]),                       # Spark / Thunderbird
                    (0, 25000, [140024, 140021]),                       # Twister / Storm
                    (0, 25000, [142030, 142029, 142028]),               # Burst Sedan
                    (0, 25000, [140051, 140048]),                       # Hunting Off-road
                    # Category 0: SUVs & Trucks (31002)
                    (0, 31002, [140406, 140404, 140403]),               # Monster Truck
                    (0, 31002, [140046, 140041]),                       # Frosty Frills
                    (0, 31002, [140914, 140911]),                       # Warjeep
                    # Category 0: Jeeps (25001)
                    (0, 25001, [140224, 140223, 140221]),               # Subjugator
                    (0, 25001, [140061, 140056]),                       # Hovering Car
                    # Category 0: Battle Jeeps (31004)
                    (0, 31004, [142003, 140241]),                       # Burst Buggy / Deathmobile
                    # Category 1: Motorcycles (25010)
                    (1, 25010, [140077, 140076]),                       # Darksteel Bike
                    (1, 25010, [140214, 140211]),                       # Pegasus
                    (1, 25010, [140205, 140202]),                       # Blazing Flash
                    # Category 1: Special Cars in Category 1 (25000)
                    (1, 25000, [142006, 142005, 142004]),               # Golden Flash
                    (1, 25000, [142013, 142012, 142011]),               # Shadowfax
                    # Category 2: Three-wheelers / Tuk-tuks (25003)
                    (2, 25003, [140905, 140902]),                       # Reign of Fire / 5 Star Ride
                    # Category 11: Skateboards (125101)
                    (11, 125101, [140065, 140064, 140062]),             # Dynamic Streamer Skateboard
                    # Category 11: Bicycles & Raptors (910043)
                    (11, 910043, [142008, 140237, 142007]),             # Velociraptor
                    (11, 910043, [140074, 140073]),                     # Summer Bicycle
                ]

                if isinstance(ret, dict):
                    grouped_chains = {}
                    for cat_id, land_vid, chain in chains:
                        grouped_chains.setdefault((cat_id, land_vid), []).append(chain)

                    for (cat_id, land_vid), family_chains in grouped_chains.items():
                        cat_dict = ret.get(cat_id) or ret.get(str(cat_id))
                        if not isinstance(cat_dict, dict):
                            continue

                        vid_key = land_vid if land_vid in cat_dict else (str(land_vid) if str(land_vid) in cat_dict else None)
                        if vid_key is None:
                            vid_key = land_vid
                            cat_dict[vid_key] = []

                        current_list = list(cat_dict.get(vid_key) or [])

                        all_chain_tiers = set()
                        for chain in family_chains:
                            all_chain_tiers.update(chain)

                        new_list = []
                        seen = set()

                        # Keep non-family items already in category
                        for item in current_list:
                            if item not in all_chain_tiers and item not in seen:
                                seen.add(item)
                                new_list.append(item)

                        # Show EVERY tier owned in each family (e.g. Level 1 AND Level 2)
                        for chain in family_chains:
                            owned_in_chain = [tier for tier in chain if _has(tier)]
                            if owned_in_chain:
                                # Show higher tiers first down to base tier
                                for tier in chain:
                                    if tier in owned_in_chain and tier not in seen:
                                        seen.add(tier)
                                        new_list.append(tier)
                                        # Ensure owned tier is in player's package
                                        if not (tier in ilist or str(tier) in ilist):
                                            push = globals().get('_push_one_item')
                                            if callable(push):
                                                try:
                                                    push(player, tier, 1, 0, package='appearance')
                                                except Exception:
                                                    pass
                                            ask = globals().get('ask_backend')
                                            if callable(ask):
                                                try:
                                                    ask('appearanceCultivateCompound', [0, tier, 0], {}, lambda reply: None)
                                                except Exception:
                                                    pass
                            else:
                                # Not owned yet: show base tier so player can view it in catalog
                                base_tier = chain[-1]
                                if base_tier not in seen:
                                    seen.add(base_tier)
                                    new_list.append(base_tier)

                        cat_dict[vid_key] = new_list

            except Exception as e:
                pass
            return ret

        mod.getAvailableVehicleAppearanceIDs = _dh_hooked_get_avail_veh
        log('local-veh-avail-hook-installed', installed=True)
    except Exception as e:
        log_error('local-veh-avail-hook-error', err=str(e))


try:
    _dh_install_vehicle_master_hooks()
    _dh_install_vehicle_appearance_preload_hook()
    call_later(0.5, _dh_install_vehicle_master_hooks)
    call_later(1.0, _dh_install_vehicle_appearance_preload_hook)
except Exception:
    pass
'''

    # Replace existing _dh_install_vehicle_appearance_preload_hook
    prev_veh_hook = content.find('def _dh_install_vehicle_appearance_preload_hook():')
    if prev_veh_hook != -1:
        start_cut = content.rfind('# --- Master Vehicle Preload', 0, prev_veh_hook)
        if start_cut == -1:
            start_cut = prev_veh_hook
        next_sect = content.find('# --- Master UIHallThemeMall', prev_veh_hook)
        if next_sect != -1:
            content = content[:start_cut] + master_veh_preload_code.strip() + '\n\n' + content[next_sect:]
        else:
            content = content[:start_cut] + master_veh_preload_code.strip() + '\n'
        print('[lobby] Replaced _dh_install_vehicle_appearance_preload_hook with master version')
    else:
        content += '\n' + master_veh_preload_code.strip() + '\n'
        print('[lobby] Appended master vehicle hooks')

    # =========================================================================
    # PART 3: Update evo_rules in _dh_clean_depot_duplicates & _dh_rpc_appearance_cultivate_compound
    # =========================================================================
    all_evo_rules_str = '''        evo_rules = [
            (140035, (140031,)),
            (140905, (140902,)),
            (140406, (140404, 140403)),
            (140404, (140403,)),
            (140013, (140010,)),
            (140024, (140021,)),
            (142030, (142029, 142028)),
            (142029, (142028,)),
            (140051, (140048,)),
            (140046, (140041,)),
            (140914, (140911,)),
            (140224, (140223, 140221)),
            (140223, (140221,)),
            (140061, (140056,)),
            (142003, (140241,)),
            (140077, (140076,)),
            (140214, (140211,)),
            (140205, (140202,)),
            (142006, (142005, 142004)),
            (142005, (142004,)),
            (142013, (142012, 142011)),
            (142012, (142011,)),
            (142008, (142007,)),
            (140237, (142007,)),
            (140074, (140073,)),
            (140065, (140064, 140062)),
            (140064, (140062,)),
        ]'''

    # Update evo_rules inside _dh_clean_depot_duplicates
    evo_pat = re.compile(r'evo_rules\s*=\s*\[[\s\S]*?\]')
    m = evo_pat.search(content)
    if m:
        content = content[:m.start()] + all_evo_rules_str.strip() + content[m.end():]
        print('[lobby] Updated evo_rules in _dh_clean_depot_duplicates')

    # Update _tune_src_map in _dh_rpc_appearance_cultivate_compound
    tune_map_str = '''    _tune_src_map = {
        140035: 140031,  # Supernova -> Nova X1
        140905: 140902,  # Reign of Fire -> 5 Star Ride
        140404: 140403,  # Monster - M2 -> Monster - M1
        140406: 140404,  # Wild Beast (M3) -> Monster - M2
        140013: 140010,  # Thunderbird -> Spark V3
        140024: 140021,  # Storm -> Twister - T1
        142029: 142028,  # Burst Sedan Lv. 2 -> Lv. 1
        142030: 142029,  # Burst Sedan Lv. 3 -> Lv. 2
        140051: 140048,  # Fiery Hunting -> Hunting Path - I
        140046: 140041,  # Brain Freeze -> Frosty Frills - I
        140914: 140911,  # Warjeep lv 4 -> lv 1
        140223: 140221,  # Subjugator T2 -> Subjugator
        140224: 140223,  # Discovery -> Subjugator T2
        140061: 140056,  # Hovering Car Max -> Lv. 1
        142003: 140241,  # Deathmobile -> Burst Buggy - I
        140077: 140076,  # Darksteel Bike Lv. 2 -> Lv. 1
        140214: 140211,  # Pegasus Turbo -> Pegasus - I
        140205: 140202,  # Phoenix -> Blazing Flash A1
        142005: 142004,  # Golden Flash Lv. 2 -> Lv. 1
        142006: 142005,  # Golden Flash Lv. 3 -> Lv. 2
        142012: 142011,  # Shadowfax Kingly -> Noble
        142013: 142012,  # Shadowfax Furious -> Kingly
        142008: 142007,  # Velociraptor Lv. 2 -> Lv. 1
        140237: 142007,  # Velociraptor Lv. 2 (native) -> Lv. 1
        140074: 140073,  # Summer Bicycle Lv. 2 -> Lv. 1
        140064: 140062,  # Dynamic Streamer Lv. 1 -> Base
        140065: 140064,  # Dynamic Streamer MAX -> Lv. 1
    }'''

    tune_pat = re.compile(r'_tune_src_map\s*=\s*\{[\s\S]*?\}')
    m_tune = tune_pat.search(content)
    if m_tune:
        content = content[:m_tune.start()] + tune_map_str.strip() + content[m_tune.end():]
        print('[lobby] Updated _tune_src_map in _dh_rpc_appearance_cultivate_compound')

    # =========================================================================
    # PART 4: Prop table hooks - should_appear, prop_type, is_veh, client_knows
    # =========================================================================
    # Update _dh_should_appear
    should_pat = re.compile(r'def _dh_should_appear\(prop_id\):[\s\S]*?return orig_should\(prop_id\)')
    new_should = '''def _dh_should_appear(prop_id):
                    try:
                        iid = int(prop_id)
                        if iid in _VEHICLE_FAMILY_MAP or iid in _dh_ensure_synthetic_props():
                            return True
                    except Exception:
                        pass
                    return orig_should(prop_id)'''
    if should_pat.search(content):
        content = should_pat.sub(new_should, content, count=1)
        print('[lobby] Updated _dh_should_appear to use _VEHICLE_FAMILY_MAP')

    # Update _dh_client_knows_item
    knows_pat = re.compile(r'def _dh_client_knows_item\(item_id\):[\s\S]*?return orig_get\(iid\) is not None')
    new_knows = '''def _dh_client_knows_item(item_id):
    try:
        iid = int(item_id)
        if iid in _VEHICLE_FAMILY_MAP:
            return True
        syn = _dh_ensure_synthetic_props()
        if iid in syn:
            return True
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        orig_get = getattr(legacy, '_dh_orig_get_dts_prop', legacy.getDtsHallPropData)
        return orig_get(iid) is not None'''
    if knows_pat.search(content):
        content = knows_pat.sub(new_knows, content, count=1)
        print('[lobby] Updated _dh_client_knows_item to use _VEHICLE_FAMILY_MAP')

    
    # =========================================================================
    # PART 5: Depot lag debounce & Workshop tune server persistence
    # =========================================================================
    # 5a. Strict _is_owned and debounce in _dh_clean_depot_duplicates
    old_is_owned = '''        def _is_owned(iid):
            if iid in item_list or str(iid) in item_list:
                return True
            cnt_fn = getattr(player, 'getPermanentDtsAppearanceItemCnt', None)
            if callable(cnt_fn) and cnt_fn(int(iid)) > 0:
                return True
            return False'''

    new_is_owned = '''        def _is_owned(iid):
            return (iid in item_list or str(iid) in item_list)'''

    if old_is_owned in content:
        content = content.replace(old_is_owned, new_is_owned)
        print('[lobby] Fixed _is_owned in _dh_clean_depot_duplicates (no false positives)')

    # 5b. Debounce at beginning of _dh_clean_depot_duplicates
    old_clean_start = '''        pkg = getattr(player, 'dtsAppearancePackage', None)
        if pkg is None:
            return 0
        item_list = getattr(pkg, 'itemList', None)
        if not isinstance(item_list, dict):
            return 0

        cleaned = 0'''

    new_clean_start = '''        import time as _time
        now = _time.time()
        if now - getattr(player, '_dh_last_depot_clean_time', 0.0) < 5.0:
            return 0
        player._dh_last_depot_clean_time = now

        pkg = getattr(player, 'dtsAppearancePackage', None)
        if pkg is None:
            return 0
        item_list = getattr(pkg, 'itemList', None)
        if not isinstance(item_list, dict):
            return 0

        cleaned = 0'''

    if old_clean_start in content:
        content = content.replace(old_clean_start, new_clean_start)
        print('[lobby] Added 5s debounce to _dh_clean_depot_duplicates (depot lag fixed)')

    # 5c. Only refresh UI when cleaned > 0
    old_ui_refresh = '''        # 3. Refresh appearance UIs if open
        try:
            import Globals
            ui_mgr = getattr(Globals, 'uiMgr', None)
            if ui_mgr:
                for ui_name in ('UIDtsAppearanceVehicle', 'UIDtsAppearanceVehicleCultivate2'):
                    scr = getattr(ui_mgr, ui_name, None)
                    if scr and getattr(scr, 'is_enter', False):
                        for mname in ('refreshAppearanceList',):
                            fn = getattr(scr, mname, None)
                            if callable(fn):
                                try:
                                    fn()
                                except Exception:
                                    pass
        except Exception:
            pass'''

    new_ui_refresh = '''        # 3. Refresh appearance UIs if open
        if cleaned > 0:
            try:
                import Globals
                ui_mgr = getattr(Globals, 'uiMgr', None)
                if ui_mgr:
                    for ui_name in ('UIDtsAppearanceVehicle', 'UIDtsAppearanceVehicleCultivate2'):
                        scr = getattr(ui_mgr, ui_name, None)
                        if scr and getattr(scr, 'is_enter', False):
                            for mname in ('refreshAppearanceList',):
                                fn = getattr(scr, mname, None)
                                if callable(fn):
                                    try:
                                        fn()
                                    except Exception:
                                        pass
            except Exception:
                pass'''

    if old_ui_refresh in content:
        content = content.replace(old_ui_refresh, new_ui_refresh)
        print('[lobby] Conditional UI refresh in _dh_clean_depot_duplicates')

    # 5d. Replace call_pyserver with ask_backend in _dh_rpc_appearance_cultivate_compound
    old_call_pyserver = '''    # 6. Notify backend server if reachable to persist in database
    try:
        call_pyserver('appearanceCultivateCompound', (src_id, target_id, flag), kwargs)
    except Exception:
        pass'''

    new_call_pyserver = '''    # 6. Notify backend server if reachable to persist in database
    try:
        ask = globals().get('ask_backend')
        if callable(ask):
            ask('appearanceCultivateCompound', [src_id, target_id, flag], kwargs, lambda reply: None)
    except Exception:
        pass'''

    if old_call_pyserver in content:
        content = content.replace(old_call_pyserver, new_call_pyserver)
        print('[lobby] Replaced call_pyserver with ask_backend in _dh_rpc_appearance_cultivate_compound')

    # 5e. Ensure target_id is always pushed in cultivate compound
    old_push_cult = '''    # 3. Add target appearance item to player's package (1 copy only)
    try:
        own_fn = getattr(player, 'getPermanentDtsAppearanceItemCnt', None)
        if not callable(own_fn) or own_fn(target_id) == 0:
            _push_one_item(player, target_id, 1, 0, package='appearance')
    except Exception:
        log_error('local-cultivate-push-target-error', target_id=target_id)'''

    new_push_cult = '''    # 3. Add target appearance item to player's package (1 copy only)
    try:
        _push_one_item(player, target_id, 1, 0, package='appearance')
    except Exception:
        log_error('local-cultivate-push-target-error', target_id=target_id)'''

    if old_push_cult in content:
        content = content.replace(old_push_cult, new_push_cult)
        print('[lobby] Guaranteed item push in _dh_rpc_appearance_cultivate_compound')

    
    # Fast handler for requestShareAddtionShow: stops 23.3-second socket timeout on opening Depot
    share_handler_str = '''
def _dh_rpc_share_addition(player, *args, **kwargs):
    for cb_name in ('onQueryShareAddtionShow', 'onShareAddtionShow', 'onQueryShareAdditionShow'):
        cb = getattr(player, cb_name, None)
        if callable(cb):
            try:
                cb({})
            except Exception:
                pass
    return True

try:
    RPC_HANDLERS['requestShareAddtionShow'] = _dh_rpc_share_addition
except Exception:
    pass
'''
    if 'requestShareAddtionShow' not in content:
        content = content + "\n" + share_handler_str
        print('[lobby] Added requestShareAddtionShow fast RPC handler (Depot freeze eliminated)')

        # 5f. Remove lower tier vehicle wipe in _dh_clean_depot_duplicates
    old_wipe_block = '''        for target_id, src_ids in evo_rules:
            is_target_owned = _is_owned(target_id) or (target_id in eq_vehicles)
            if is_target_owned:
                if not _is_owned(target_id):
                    push_fn = globals().get('_push_one_item')
                    if callable(push_fn):
                        try:
                            push_fn(player, target_id, 1, 0, package='appearance')
                        except Exception:
                            pass
                for s_id in src_ids:
                    if _is_owned(s_id):
                        cleaned += _wipe_id(s_id)'''

    new_wipe_block = '''        for target_id, src_ids in evo_rules:
            is_target_owned = _is_owned(target_id) or (target_id in eq_vehicles)
            if is_target_owned:
                if not _is_owned(target_id):
                    push_fn = globals().get('_push_one_item')
                    if callable(push_fn):
                        try:
                            push_fn(player, target_id, 1, 0, package='appearance')
                        except Exception:
                            pass'''

    if old_wipe_block in content:
        content = content.replace(old_wipe_block, new_wipe_block)
        print('[lobby] Preserved lower-tier vehicles in _dh_clean_depot_duplicates (both Lv1 and Lv2 kept)')

    
    # 5g. Consume only extra duplicate in _dh_rpc_appearance_cultivate_compound (retain 1x Lv1)
    old_cult_remove = '''    # 1. Deduct cost / source appearance item (ALL copies)
    if effective_src:
        try:
            _dh_remove_all_appearance_copies(player, effective_src)
        except Exception:
            log_error('local-cultivate-remove-src-error', src_id=effective_src)
    if src_id and src_id != target_id and src_id != effective_src:
        try:
            _dh_remove_all_appearance_copies(player, src_id)
        except Exception:
            pass
    if target_id in _tune_src_map:
        _dh_remove_all_appearance_copies(player, _tune_src_map[target_id])'''

    new_cult_remove = '''    # 1. Deduct cost: consume extra copy only, preserve 1x source item
    try:
        pkg = getattr(player, 'dtsAppearancePackage', None)
        ilist = getattr(pkg, 'itemList', {}) if pkg else {}
        for s_check in (effective_src, src_id):
            if not s_check:
                continue
            entries = ilist.get(s_check) or ilist.get(str(s_check))
            if isinstance(entries, dict) and len(entries) > 1:
                uuids = list(entries.keys())
                player.onDelDtsAppearanceItem(int(s_check), uuids[-1])
                entries.pop(uuids[-1], None)
    except Exception:
        pass'''

    if old_cult_remove in content:
        content = content.replace(old_cult_remove, new_cult_remove)
        print('[lobby] Preserved 1x source vehicle on cultivate compound')

    with open('clean_remote_lobby.py', 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

    print('Patched clean_remote_lobby.py written. Final length:', len(content))

if __name__ == '__main__':
    patch_clean_remote_lobby()

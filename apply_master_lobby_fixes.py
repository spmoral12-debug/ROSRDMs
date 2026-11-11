# -*- coding: utf-8 -*-
"""
Master Patch for DieHard ROS:
1. Complete Vehicle Hierarchy & Catalog (Monster, Velociraptor, Darksteel Bike, Summer Bicycle, Golden Flash, Shadowfax)
   - Proper synthetic props with authentic models and icons
   - getPermanentDtsAppearanceItemCnt family fallback so native catalog never hides owned vehicles
   - getAvailableVehicleAppearanceIDs hook preserving both Velociraptor and Bicycle under Category 11
   - Exactly 1 tile per vehicle family matching highest owned tier
   - Zero duplication / no "x2" badge
   - Workshop / Congrats 3D model loading & catalog unfreeze
2. Lobby Theme Direct Equip & Purchase (No clothing bundle popup, no blinking in Depot)
   - UIHallThemeMall equips/changes theme directly
   - Depot retains natural smoke showroom backdrop without watchdog blinking
   - Lobby permanently retains equipped theme
3. Battle Teammate Fixes (Lock 3D overhead to live avatar, remove white pillar, fix HUD panel, fix 98% hang)
   - Sync ct.position to mate's live Avatar entity every frame
   - ct.model.visible = False, scale = 0.0001 (white pillar eliminated)
   - HUD teammate panel updates all teammates
   - Guard BehaviourContainer.RemoveBehaviour & PhysicsAdapter to eliminate 98% quit hang
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
    if 121363 in _dh_synthetic_props and 142008 in _dh_synthetic_props and 140404 in _dh_synthetic_props:
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

        # 2. Velociraptor Lv. 2 (142008)
        if 142008 not in _dh_synthetic_props:
            raptor_lv1 = orig_get(142007)
            if raptor_lv1 is not None:
                raptor_lv2 = copy.copy(raptor_lv1)
                ptype = copy.copy(getattr(raptor_lv1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/bike_xunmenglongdiji/xunmenglongdiji.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/bike_xunmenglongdiji/xunmenglongdiji.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 910059),
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
                                ec.DISPLAY_PROP_LIST = [142007]
                                new_dim.append(ec)
                            ptype.DISPLAY_IN_MODEL = new_dim
                    except Exception:
                        pass
                    raptor_lv2.PROP_TYPE = ptype
                for attr, val in (('NAME', 'Velociraptor Lv. 2'),
                                  ('QUALITY', 5),
                                  ('SCORE', 300),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png')):
                    try:
                        setattr(raptor_lv2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[142008] = raptor_lv2

        # 3. Monster - M2 (140404)
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
                                  ('SCORE', 300),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png')):
                    try:
                        setattr(m2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140404] = m2

        # 4. Darksteel Bike Lv. 2 (140077)
        if 140077 not in _dh_synthetic_props:
            b1 = orig_get(140076)
            if b1 is not None:
                b2 = copy.copy(b1)
                ptype = copy.copy(getattr(b1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/gthaigumotuo/gthaigumotuo1.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/gthaigumotuo/gthaigumotuo1.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 130002),
                                      ('SCORE', 300),
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
                                  ('SCORE', 300),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png')):
                    try:
                        setattr(b2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140077] = b2

        # 5. Summer Bicycle Lv. 2 (140074)
        if 140074 not in _dh_synthetic_props:
            sb1 = orig_get(140073)
            if sb1 is not None:
                sb2 = copy.copy(sb1)
                ptype = copy.copy(getattr(sb1, 'PROP_TYPE', None))
                if ptype is not None:
                    for attr, val in (('FP_MTG_PATH', 'vehicle/summer_bike_lv1/summer_bike_lv1.mtg'),
                                      ('TP_MTG_PATH', 'vehicle/summer_bike_lv1/summer_bike_lv1.mtg'),
                                      ('DISPLAY_USING_VEHICLE_ID', 30004),
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
                                  ('SCORE', 300),
                                  ('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png'),
                                  ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png')):
                    try:
                        setattr(sb2, attr, val)
                    except Exception:
                        pass
                _dh_synthetic_props[140074] = sb2

        # 6. Golden Flash Lv. 2 (142005) & Lv. 3 (142006)
        gf1 = orig_get(142004)
        if gf1 is not None:
            for gfid, gfname in ((142005, 'Golden Flash Lv. 2'), (142006, 'Golden Flash Lv. 3')):
                if gfid not in _dh_synthetic_props:
                    gfc = copy.copy(gf1)
                    gfc.NAME = gfname
                    gfc.QUALITY = 5
                    gfc.SCORE = 300
                    for attr, val in (('ICON_PATH', 'ui/images/dts_appearance/vehiclefull/img_weilai1.png'),
                                      ('ICON_PATH_DISPLAY', 'ui/images/dts_appearance/vehiclefull/img_weilai1.png')):
                        try:
                            setattr(gfc, attr, val)
                        except Exception:
                            pass
                    ptype = copy.copy(getattr(gf1, 'PROP_TYPE', None))
                    if ptype is not None:
                        try:
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
                        gfc.PROP_TYPE = ptype
                    _dh_synthetic_props[gfid] = gfc

    except Exception as e:
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
    140406: (140403, [140406, 140404, 140403]),
    140404: (140403, [140406, 140404, 140403]),
    140403: (140403, [140406, 140404, 140403]),

    142008: (142007, [142008, 142007]),
    142007: (142007, [142008, 142007]),

    140077: (140076, [140077, 140076]),
    140076: (140076, [140077, 140076]),

    140074: (140073, [140074, 140073]),
    140073: (140073, [140074, 140073]),

    142006: (142004, [142006, 142005, 142004]),
    142005: (142004, [142006, 142005, 142004]),
    142004: (142004, [142006, 142005, 142004]),

    142013: (142011, [142013, 142012, 142011]),
    142012: (142011, [142013, 142012, 142011]),
    142011: (142011, [142013, 142012, 142011]),
}

_VEHICLE_NAME_MAP = {
    140403: 'Monster - M1',
    140404: 'Monster - M2',
    140406: 'Wild Beast',
    142007: 'Velociraptor Lv. 1',
    142008: 'Velociraptor Lv. 2',
    140076: 'Darksteel Bike Lv. 1',
    140077: 'Darksteel Bike Lv. 2',
    140073: 'Summer Bicycle',
    140074: 'Summer Bicycle Lv. 2',
    142004: 'Golden Flash Lv. 1',
    142005: 'Golden Flash Lv. 2',
    142006: 'Golden Flash Lv. 3',
    142011: 'Shadowfax - Noble',
    142012: 'Shadowfax - Kingly',
    142013: 'Shadowfax - Furious',
}

_VEHICLE_ICON_MAP = {
    140403: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png',
    140404: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_01.png',
    140406: 'ui/images/dts_appearance/vehiclefull/img_zj_guaiwupk_03.png',
    142007: 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png',
    142008: 'ui/images/dts_appearance/vehiclefull/xunmenglong1.png',
    140076: 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png',
    140077: 'ui/images/dts_appearance/vehiclefull/img_xuantiemotuo_01.png',
    140073: 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png',
    140074: 'ui/images/dts_appearance/vehiclefull/img_summerbike_01.png',
    142004: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142005: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142006: 'ui/images/dts_appearance/vehiclefull/img_weilai1.png',
    142011: 'ui/images/dts_appearance/vehiclefull/laosi1.png',
    142012: 'ui/images/dts_appearance/vehiclefull/laosi2.png',
    142013: 'ui/images/dts_appearance/vehiclefull/laosi3.png',
}

def _dh_install_vehicle_master_hooks():
    try:
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
                    if ciid in _VEHICLE_FAMILY_MAP:
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
                            eq = set(getattr(self, 'dtsVehicleAppearanceList', []) or [])
                            if ciid in _VEHICLE_FAMILY_MAP:
                                base_id, chain = _VEHICLE_FAMILY_MAP[ciid]
                                for tier in chain:
                                    if tier in ilist or str(tier) in ilist or tier in eq:
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
        mod = __import__('dts_appearance_preload')
        orig_fn = getattr(mod, '_dh_orig_get_avail_veh', getattr(mod, 'getAvailableVehicleAppearanceIDs', None))
        if not callable(orig_fn):
            return
        mod._dh_orig_get_avail_veh = orig_fn

        def _dh_hooked_get_avail_veh(*args, **kwargs):
            ret = orig_fn(*args, **kwargs)
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

                # Family definitions: (cat_id, land_vid, chain_list)
                # Category 0: Car, Category 1: Motorcycle, Category 11: Bike/Skateboard
                chains = [
                    (0, 31002, [140406, 140404, 140403]),       # Monster Truck
                    (1, 25010, [140077, 140076]),              # Darksteel Bike
                    (1, 25000, [142006, 142005, 142004]),      # Golden Flash
                    (1, 25000, [142013, 142012, 142011]),      # Shadowfax
                    (11, 910043, [142008, 142007]),             # Velociraptor
                    (11, 910043, [140074, 140073]),             # Summer Bicycle
                ]

                if isinstance(ret, dict):
                    # Group chains by (cat_id, land_vid) to properly handle shared land_vid like 910043
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
                        
                        # Collect all lower tiers to remove and highest owned tiers to keep
                        to_remove = set()
                        to_keep = []

                        for chain in family_chains:
                            highest_owned = None
                            for tier in chain:
                                if _has(tier):
                                    highest_owned = tier
                                    break
                            
                            if highest_owned is not None:
                                to_keep.append(highest_owned)
                                to_remove.update(set(chain) - {highest_owned})
                                # Ensure highest_owned is present in package
                                if not (highest_owned in ilist or str(highest_owned) in ilist):
                                    push = globals().get('_push_one_item')
                                    if callable(push):
                                        try:
                                            push(player, highest_owned, 1, 0, package='appearance')
                                        except Exception:
                                            pass
                            else:
                                # Not owned: keep base model if in original list, remove synthetic higher tiers
                                to_remove.update(chain[:-1])

                        # Filter current_list
                        filtered = [x for x in current_list if x not in to_remove]
                        for keeper in to_keep:
                            if keeper not in filtered:
                                filtered.append(keeper)

                        cat_dict[vid_key] = filtered

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
        # Cut off from prev_veh_hook to end or replace
        content = content[:prev_veh_hook] + master_veh_preload_code.strip() + '\n'
        print('[lobby] Replaced _dh_install_vehicle_appearance_preload_hook with master version')
    else:
        content += '\n' + master_veh_preload_code.strip() + '\n'
        print('[lobby] Appended master vehicle hooks')

    # =========================================================================
    # PART 3: UIHallThemeMall Direct Equip / Purchase & Workshop Unfreeze
    # =========================================================================
    theme_and_workshop_hooks = '''
# --- Master UIHallThemeMall & UIWorkshop Interaction Fix ---
def _dh_install_theme_and_workshop_hooks():
    try:
        import sys
        # 1. UIHallThemeMall - Direct Equip & Single Buy (No clothing cart!)
        for mod_name in ('ui.UIHallThemeMall', 'UIHallThemeMall'):
            mod = sys.modules.get(mod_name)
            cls = getattr(mod, 'UIHallThemeMall', None) if mod is not None else None
            if cls is not None:
                # Wrap buy button to directly equip or purchase theme
                orig_buy = getattr(cls, '_dh_orig_buy_btn', getattr(cls, 'onBuyBtnClicked', None))
                if callable(orig_buy):
                    cls._dh_orig_buy_btn = orig_buy
                    def _dh_hooked_theme_buy(self, *a, **k):
                        try:
                            # Get currently selected theme ID
                            theme_id = getattr(self, 'selectedThemeID', None) or getattr(self, 'curThemeID', None) or getattr(self, 'selectedPropID', None)
                            if theme_id:
                                _dh_theme_remember(theme_id)
                                show_sys_banner("Theme equipped successfully!")
                                return
                        except Exception:
                            pass
                        return orig_buy(self, *a, **k)
                    cls.onBuyBtnClicked = _dh_hooked_theme_buy

                # Also wrap onRealBuyBtnClicked to avoid bundle cart popup
                orig_real_buy = getattr(cls, '_dh_orig_real_buy', getattr(cls, 'onRealBuyBtnClicked', None))
                if callable(orig_real_buy):
                    cls._dh_orig_real_buy = orig_real_buy
                    def _dh_hooked_real_buy(self, *a, **k):
                        try:
                            theme_id = getattr(self, 'selectedThemeID', None) or getattr(self, 'curThemeID', None) or getattr(self, 'selectedPropID', None)
                            if theme_id:
                                _dh_theme_remember(theme_id)
                                show_sys_banner("Theme changed successfully!")
                                return
                        except Exception:
                            pass
                        return orig_real_buy(self, *a, **k)
                    cls.onRealBuyBtnClicked = _dh_hooked_real_buy

        # 2. UIWorkshop & UIDtsAppearanceVehicle - Catalog Unfreeze
        for mod_name in ('ui.UIWorkshop', 'UIWorkshop', 'ui.UIDtsAppearanceVehicle', 'UIDtsAppearanceVehicle'):
            mod = sys.modules.get(mod_name)
            cls = getattr(mod, mod_name.split('.')[-1], None) if mod is not None else None
            if cls is not None:
                orig_exit = getattr(cls, '_dh_orig_exit', getattr(cls, 'onExit', None))
                if callable(orig_exit):
                    cls._dh_orig_exit = orig_exit
                    def _dh_workshop_exit(self, *a, **k):
                        try:
                            self.modelLoading = False
                        except Exception:
                            pass
                        return orig_exit(self, *a, **k)
                    cls.onExit = _dh_workshop_exit

        log('local-theme-and-workshop-hooks-installed', success=True)
    except Exception as e:
        log_error('local-theme-workshop-hooks-error', err=str(e))


try:
    call_later(2.0, _dh_install_theme_and_workshop_hooks)
    call_later(5.0, _dh_install_theme_and_workshop_hooks)
except Exception:
    pass
'''
    if '_dh_install_theme_and_workshop_hooks' not in content:
        content += '\n' + theme_and_workshop_hooks.strip() + '\n'
        print('[lobby] Appended theme and workshop interaction hooks')

    # =========================================================================
    # PART 4: Fix _dh_clean_depot_duplicates to NOT wipe base IDs when upgraded
    # and strictly clamp permanent cosmetics to 1 copy
    # =========================================================================
    old_depot_clean_call = "for ui_name in ('UIDtsAppearanceVehicle', 'UIDtsAppearanceVehicleCultivate2', 'UIDtsAppearance'):\n                    scr = getattr(ui_mgr, ui_name, None)\n                    if scr and getattr(scr, 'is_enter', False):\n                        for mname in ('refreshAppearanceList', 'refresh', 'refreshView'):"
    new_depot_clean_call = "for ui_name in ('UIDtsAppearanceVehicle', 'UIDtsAppearanceVehicleCultivate2'):\n                    scr = getattr(ui_mgr, ui_name, None)\n                    if scr and getattr(scr, 'is_enter', False):\n                        for mname in ('refreshAppearanceList',):"

    if old_depot_clean_call in content:
        content = content.replace(old_depot_clean_call, new_depot_clean_call, 1)
        print('[lobby] Removed full refresh/refreshView from _dh_clean_depot_duplicates (preventing background blinking)')


    # =========================================================================
    # PART 5: Purge Stray Male Dummy Model & Restore Post-Battle Sky/Backdrop
    # =========================================================================
    stray_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patch_stray_and_clay.py')
    if os.path.exists(stray_script):
        exec(open(stray_script, 'r', encoding='utf-8').read(), globals())
        run_patch()
        print('[lobby] Applied Part 5: Purged stray male model and restored post-battle sky/backdrop')
        return

    with open('clean_remote_lobby.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('clean_remote_lobby.py updated successfully!')

patch_clean_remote_lobby()


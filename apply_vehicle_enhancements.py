# -*- coding: utf-8 -*-
import os

print("=== APPLYING VEHICLE ENHANCEMENTS TO CLEAN_REMOTE_BATTLE.PY ===")

patch_marker = "# ROS REDEMPTION - VEHICLE SYSTEM OVERHAUL"

with open('clean_remote_battle.py', 'r', encoding='utf-8') as f:
    content = f.read()

if patch_marker in content:
    print("Vehicle enhancements already present, stripping old version...")
    idx = content.find(patch_marker)
    content = content[:idx].rstrip() + "\n\n"

vehicle_patch_code = '''# ==============================================================================
# ROS REDEMPTION - VEHICLE SYSTEM OVERHAUL
# 1. Car Skin System (reqDyeingVehicle handler, boarding auto-skin, /skin command)
# 2. Turbo Boost (onAccStart / onAccEnd, Shift hotkey, 2.4x driveForce, nitro flames)
# 3. Fuel / Gas Consumption (dynamic consumption, faster on turbo, out-of-gas, /fuel)
# 4. Engine Audio Smoothing (no screeching/RPM spikes, eliminates stutter/lag)
# ==============================================================================

# Global vehicle states
_car_turbo_state = {}
_car_empty_gas = set()

# --- 1. CAR SKIN SYSTEM ---
try:
    def redemption_apply_car_skin(car, appearance_id):
        if car is None:
            return False
        try:
            aid = int(appearance_id or 0)
            if not aid:
                return False
            old_aid = getattr(car, 'tpsVehicleID', 0)
            car.tpsVehicleID = aid

            veh_dict = globals().get('_vehicles')
            if isinstance(veh_dict, dict) and getattr(car, 'id', None) in veh_dict:
                veh_dict[car.id]['tps'] = aid

            if hasattr(car, 'set_tpsVehicleID'):
                try:
                    car.set_tpsVehicleID(old_aid)
                except Exception:
                    pass

            for method in ('onVehicleAppearanceChanged', 'changeAppearance', 'onDyeingVehicle', 'dyeingVehicle'):
                fn = getattr(car, method, None)
                if callable(fn):
                    try:
                        fn(aid)
                    except Exception:
                        pass

            try:
                assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
                if assemble is not None:
                    for assem_fn in ('resetAppearance', 'initAppearance', 'changeAppearance'):
                        m = getattr(assemble, assem_fn, None)
                        if callable(m):
                            try:
                                m(aid)
                            except Exception:
                                pass
            except Exception:
                pass

            log('local-battle-car-skin-applied', vehicle=getattr(car, 'id', 0), skin=aid)
            return True
        except Exception as ex:
            log_error('local-battle-car-skin-error', err=str(ex))
            return False

    def redemption_req_dyeing_vehicle(player, vehicle_id=0, appearance_id=0, *args, **kwargs):
        try:
            vid = int(vehicle_id or 0)
            aid = int(appearance_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            if car is None:
                try:
                    import BigWorld
                    car = BigWorld.entities.get(vid)
                except Exception:
                    car = None
            if car is not None and aid:
                redemption_apply_car_skin(car, aid)
                if hasattr(player, 'dyeingVehicle'):
                    try:
                        player.dyeingVehicle(vid, aid)
                    except Exception:
                        pass
                elif hasattr(player, 'onDyeingVehicle'):
                    try:
                        player.onDyeingVehicle(vid, aid)
                    except Exception:
                        pass
                tip_text('#c00e5ffCar skin applied!#n')
                return True
        except Exception:
            pass
        return True

    _rh = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_rh, dict):
        _rh['reqDyeingVehicle'] = redemption_req_dyeing_vehicle
        _rh['reqPlayVehicleTransformExitEff'] = lambda *a, **k: True
        _rh['reqWearVehicleTransformCloth'] = lambda *a, **k: True

    _orig_seat_player = globals().get('seat_player')
    if callable(_orig_seat_player):
        def redemption_seat_player_skin(player, car, socket, *args, **kwargs):
            res = _orig_seat_player(player, car, socket, *args, **kwargs)
            try:
                driver_socket = globals().get('VEHICLE_DRIVER_SOCKET', 'Driver')
                if socket == driver_socket and car is not None:
                    skins_dict = getattr(player, 'landVehicleID2AppearanceIDDict', None)
                    chosen_skin = None
                    if isinstance(skins_dict, dict):
                        char_type = int(getattr(car, 'characterType', 0) or 0)
                        if char_type in skins_dict:
                            chosen_skin = skins_dict[char_type]
                        elif skins_dict:
                            chosen_skin = list(skins_dict.values())[0]
                    if not chosen_skin:
                        app_list = getattr(player, 'dtsVehicleAppearanceList', None)
                        if app_list:
                            chosen_skin = app_list[0]
                    if chosen_skin:
                        call_later(0.2, redemption_apply_car_skin, car, chosen_skin)
            except Exception:
                pass
            return res

        globals()['seat_player'] = redemption_seat_player_skin

    log('ros-redemption-fix', fix='car skin system installed')
except Exception:
    pass


# --- 2. TURBO / NITRO BOOST SYSTEM ---
try:
    def redemption_nos_start(entity_id, *args):
        try:
            vid = int(entity_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            if car is None:
                return False
            if vid in _car_empty_gas:
                tip_text('#cff2222Cannot boost: Out of gas!#n')
                return False

            _car_turbo_state[vid] = True

            buffs = getattr(car, 'vehicleBuff', None)
            if buffs is not None:
                buffs['driveForceBuff'] = 2.4
                buffs['maxSpeedBuff'] = 1.6
                buffs['throttleBuff'] = 1.5

            if callable(globals().get('vehicle_engine')):
                engine = vehicle_engine(car)
                if engine is not None:
                    setattr(engine, 'nosOpen', True)
                    if hasattr(engine, 'startNOS'):
                        try:
                            engine.startNOS()
                        except Exception:
                            pass

            if callable(globals().get('show_nos')):
                show_nos(car, True)

            log('local-battle-turbo-start', vehicle=vid)
            return True
        except Exception:
            return False

    def redemption_nos_end(entity_id, *args):
        try:
            vid = int(entity_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            _car_turbo_state[vid] = False
            if car is None:
                return False

            buffs = getattr(car, 'vehicleBuff', None)
            if buffs is not None:
                buffs['driveForceBuff'] = 1.0
                buffs['maxSpeedBuff'] = 1.0
                buffs['throttleBuff'] = 1.0

            if callable(globals().get('vehicle_engine')):
                engine = vehicle_engine(car)
                if engine is not None:
                    setattr(engine, 'nosOpen', False)
                    if hasattr(engine, 'stopNOS'):
                        try:
                            engine.stopNOS()
                        except Exception:
                            pass

            if callable(globals().get('show_nos')):
                show_nos(car, False)

            log('local-battle-turbo-end', vehicle=vid)
            return True
        except Exception:
            return False

    ccc = globals().get('CAR_CELL_CALLS')
    if isinstance(ccc, dict):
        ccc['onAccStart'] = redemption_nos_start
        ccc['onAccEnd'] = redemption_nos_end

    globals()['car_nos_on'] = redemption_nos_start
    globals()['car_nos_off'] = redemption_nos_end

    log('ros-redemption-fix', fix='turbo boost system installed')
except Exception:
    pass


# --- 3. VEHICLE FUEL / GAS SYSTEM ---
try:
    def _dh_car_fuel_monitor():
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                if car is not None and not getattr(car, 'vIsDead', False):
                    cur_fuel = getattr(car, 'fuelAmount', None)
                    if cur_fuel is None or (cur_fuel <= 0.0 and vid not in _car_empty_gas):
                        car.fuelAmount = 100.0
                        cur_fuel = 100.0

                    if cur_fuel > 0.0:
                        speed = vehicle_speed(car) if callable(globals().get('vehicle_speed')) else 0.0
                        is_turbo = _car_turbo_state.get(vid, False)

                        if is_turbo:
                            burn = 1.8
                        elif speed > 5.0:
                            burn = 0.35
                        elif speed > 0.5:
                            burn = 0.15
                        else:
                            burn = 0.04

                        new_fuel = max(0.0, cur_fuel - burn)
                        old_fuel = car.fuelAmount
                        car.fuelAmount = round(new_fuel, 2)

                        if hasattr(car, 'set_fuelAmount'):
                            try:
                                car.set_fuelAmount(old_fuel)
                            except Exception:
                                pass
                        if hasattr(car, 'onUpdateFuelAmount'):
                            try:
                                car.onUpdateFuelAmount(new_fuel)
                            except Exception:
                                pass
                        if hasattr(player, 'onUpdateVehicleGas'):
                            try:
                                player.onUpdateVehicleGas(vid, int(new_fuel))
                            except Exception:
                                pass

                        if new_fuel <= 0.0:
                            _car_empty_gas.add(vid)
                            redemption_nos_end(vid)
                            buffs = getattr(car, 'vehicleBuff', None)
                            if buffs is not None:
                                buffs['driveForceBuff'] = 0.0
                                buffs['throttleBuff'] = 0.0
                            tip_text('#cff2222Vehicle out of fuel!#n')
                            log('local-battle-vehicle-out-of-gas', vehicle=vid)
        except Exception:
            pass
        call_later(0.5, _dh_car_fuel_monitor)

    call_later(2.0, _dh_car_fuel_monitor)
    log('ros-redemption-fix', fix='fuel consumption monitor installed')
except Exception:
    pass


# --- 4. ENGINE AUDIO & SOUND STUTTER FIX ---
try:
    _orig_steady_my_car = globals().get('steady_my_car')
    def redemption_steady_and_smooth_sound():
        res = _orig_steady_my_car() if callable(_orig_steady_my_car) else False
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                if car is not None:
                    try:
                        tpsound = car.gameObject.GetComponent('VehicleTPSound')
                        if tpsound is not None:
                            if hasattr(tpsound, 'enabled'):
                                tpsound.enabled = False
                    except Exception:
                        pass

                    if callable(globals().get('vehicle_engine')):
                        engine = vehicle_engine(car)
                        if engine is not None:
                            kmh = vehicle_speed(car) if callable(globals().get('vehicle_speed')) else 0.0
                            is_turbo = _car_turbo_state.get(vid, False)
                            target_rpm = 1000.0 + min(6500.0, kmh * 72.0) + (1200.0 if is_turbo else 0.0)

                            cur_sound_rpm = float(getattr(engine, 'soundRpm', 0.0) or target_rpm)
                            if cur_sound_rpm > 10000.0 or cur_sound_rpm < 400.0:
                                engine.soundRpm = target_rpm
                            else:
                                engine.soundRpm = round(cur_sound_rpm * 0.75 + target_rpm * 0.25, 1)

                            cur_gear = int(getattr(engine, 'gear', 1) or 1)
                            if kmh > 60.0 and cur_gear < 4:
                                engine.gear = 5
        except Exception:
            pass
        return res

    globals()['steady_my_car'] = redemption_steady_and_smooth_sound
    log('ros-redemption-fix', fix='engine sound smoothing and stutter fix installed')
except Exception:
    pass


# --- 5. HOTKEYS & CHAT COMMANDS (Shift Turbo, /fuel, /skin) ---
try:
    import ctypes
    _u32 = ctypes.windll.user32
    _shift_was_down = [False]

    def redemption_vehicle_hotkey_tick():
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                # VK_SHIFT is 0x10
                shift_down = bool(_u32.GetAsyncKeyState(0x10) & 0x8000)
                if shift_down and not _shift_was_down[0]:
                    _shift_was_down[0] = True
                    redemption_nos_start(vid)
                elif not shift_down and _shift_was_down[0]:
                    _shift_was_down[0] = False
                    redemption_nos_end(vid)
            else:
                _shift_was_down[0] = False
        except Exception:
            pass
        call_later(0.1, redemption_vehicle_hotkey_tick)

    call_later(2.0, redemption_vehicle_hotkey_tick)

    _orig_icc = globals().get('install_chat_commands')
    def redemption_vehicle_install_chat_commands(player):
        if callable(_orig_icc):
            _orig_icc(player)
        try:
            _cmds = globals().get('_chat_commands')
            if isinstance(_cmds, dict):
                def _cmd_fuel(p, a):
                    vid = getattr(p, 'vehicleEntID', 0)
                    car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                    if car is not None:
                        car.fuelAmount = 100.0
                        _car_empty_gas.discard(vid)
                        buffs = getattr(car, 'vehicleBuff', None)
                        if buffs is not None:
                            buffs['driveForceBuff'] = 1.0
                            buffs['throttleBuff'] = 1.0
                        if hasattr(car, 'set_fuelAmount'):
                            car.set_fuelAmount(0.0)
                        tip_text('#c00ff00Fuel refilled to 100%!#n')
                        return 'Fuel refilled to 100%!'
                    return 'Not inside a vehicle.'

                def _cmd_skin(p, a):
                    vid = getattr(p, 'vehicleEntID', 0)
                    car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                    if car is None:
                        return 'Not inside a vehicle.'
                    parts = str(a or '').split()
                    skin_id = int(parts[0]) if parts and parts[0].isdigit() else 142080
                    redemption_apply_car_skin(car, skin_id)
                    tip_text('#c00e5ffVehicle skin set to %d!#n' % skin_id)
                    return 'Vehicle skin set to %d!' % skin_id

                _cmds['fuel'] = _cmd_fuel
                _cmds['gas'] = _cmd_fuel
                _cmds['skin'] = _cmd_skin
                _cmds['carskin'] = _cmd_skin
        except Exception:
            pass
        return True

    globals()['install_chat_commands'] = redemption_vehicle_install_chat_commands
    log('ros-redemption-fix', fix='vehicle hotkeys and commands installed')
except Exception:
    pass

log('ros-redemption-vehicle-system-complete-active', status='ready')
'''

new_content = content + "\n\n" + vehicle_patch_code

# Test compile before saving
compile(new_content.encode('utf-8'), 'clean_remote_battle', 'exec')
print("Syntax verification passed successfully!")

with open('clean_remote_battle.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Saved clean_remote_battle.py! Total length: %d bytes" % len(new_content))


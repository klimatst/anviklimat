"""Small, isolated server calculation for the refrigerant pressure ruler."""

import math

import anvil.server


REFRIGERANT_RULER_DATA = [
  {"code": "R600a", "name": "R600a изобутан", "type": "Бытовые холодильники", "bp": -11.7, "tc": 134.7, "pc": 36.3},
  {"code": "R134a", "name": "R134a тетрафторэтан", "type": "Старые холодильники, авто", "bp": -26.1, "tc": 101.1, "pc": 40.6},
  {"code": "R290", "name": "R290 пропан", "type": "Холодильники, моноблоки, тепловые насосы", "bp": -42.1, "tc": 96.7, "pc": 42.5},
  {"code": "R12", "name": "R12", "type": "Старые системы, запрещён/ограничен", "bp": -29.8, "tc": 112.0, "pc": 41.4},
  {"code": "R22", "name": "R22", "type": "Старые кондиционеры", "bp": -40.8, "tc": 96.1, "pc": 49.9},
  {"code": "R404A", "name": "R404A", "type": "Коммерческий холод", "bp": -46.5, "tc": 72.1, "pc": 37.3},
  {"code": "R507A", "name": "R507A", "type": "Коммерческий холод", "bp": -46.7, "tc": 70.9, "pc": 37.1},
  {"code": "R410A", "name": "R410A", "type": "Кондиционеры", "bp": -51.6, "tc": 72.5, "pc": 49.0},
  {"code": "R32", "name": "R32", "type": "Современные кондиционеры", "bp": -51.7, "tc": 78.1, "pc": 57.8},
  {"code": "R407C", "name": "R407C", "type": "Кондиционеры, смесь с глайдом", "bp": -43.6, "tc": 86.7, "pc": 46.3},
  {"code": "R152a", "name": "R152a", "type": "Альтернативный хладагент", "bp": -24.0, "tc": 113.3, "pc": 45.2},
  {"code": "R1234yf", "name": "R1234yf", "type": "Автокондиционеры", "bp": -29.5, "tc": 94.7, "pc": 33.8},
  {"code": "R1234ze", "name": "R1234ze(E)", "type": "Чиллеры, низкий GWP", "bp": -19.0, "tc": 109.4, "pc": 36.4},
  {"code": "R717", "name": "R717 аммиак", "type": "Промышленный холод", "bp": -33.3, "tc": 132.4, "pc": 113.5},
  {"code": "R744", "name": "R744 CO₂", "type": "CO₂, транскритические системы", "bp": -78.5, "tc": 31.0, "pc": 73.8},
  {"code": "R600", "name": "R600 бутан", "type": "Редко, углеводород", "bp": -0.5, "tc": 152.0, "pc": 38.0},
  {"code": "R1270", "name": "R1270 пропилен", "type": "Низкотемпературный холод", "bp": -47.7, "tc": 91.1, "pc": 46.0},
  {"code": "R502", "name": "R502", "type": "Старый коммерческий холод", "bp": -45.4, "tc": 82.2, "pc": 40.7}
]
REFRIGERANTS_BY_CODE = {item["code"]: item for item in REFRIGERANT_RULER_DATA}
RULER_ATMOSPHERIC_PRESSURE_BAR = 1.01325


def _ruler_pressure_abs(ref, temperature_c):
  boiling_k = ref["bp"] + 273.15
  critical_k = ref["tc"] + 273.15
  slope = math.log(ref["pc"] / RULER_ATMOSPHERIC_PRESSURE_BAR) / (
    (1.0 / boiling_k) - (1.0 / critical_k)
  )
  intercept = math.log(RULER_ATMOSPHERIC_PRESSURE_BAR) + slope / boiling_k
  temperature_k = temperature_c + 273.15
  return math.exp(intercept - slope / temperature_k)


@anvil.server.callable
def calculate_refrigerant_ruler(code, mode, raw_value, include_options=False):
  """Approximate a pressure-temperature ruler from its reference points."""
  if not isinstance(code, str) or code not in REFRIGERANTS_BY_CODE:
    return {"ok": False, "message": "Выберите хладагент из списка."}
  if mode not in ("pressure", "temperature"):
    return {"ok": False, "message": "Выберите направление пересчёта."}
  if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
    return {"ok": False, "message": "Введите давление или температуру числом."}
  try:
    value = float(str(raw_value).strip().replace(" ", "").replace(",", "."))
  except ValueError:
    return {"ok": False, "message": "Введите давление или температуру числом."}
  if not math.isfinite(value):
    return {"ok": False, "message": "Введите конечное числовое значение."}

  refrigerant = REFRIGERANTS_BY_CODE[code]
  minimum_temp = max(refrigerant["bp"] - 30.0, -80.0)
  maximum_temp = min(refrigerant["tc"] - 5.0, 90.0)
  minimum_pressure = max(
    -0.99,
    min(_ruler_pressure_abs(refrigerant, minimum_temp) - RULER_ATMOSPHERIC_PRESSURE_BAR, 0.0)
  )
  maximum_pressure = min(
    max(_ruler_pressure_abs(refrigerant, maximum_temp) - RULER_ATMOSPHERIC_PRESSURE_BAR, 1.0),
    80.0
  )

  if mode == "pressure":
    pressure_gauge = min(max(value, minimum_pressure), maximum_pressure)
    pressure_absolute = max(pressure_gauge + RULER_ATMOSPHERIC_PRESSURE_BAR, 0.02)
    boiling_k = refrigerant["bp"] + 273.15
    critical_k = refrigerant["tc"] + 273.15
    slope = math.log(refrigerant["pc"] / RULER_ATMOSPHERIC_PRESSURE_BAR) / (
      (1.0 / boiling_k) - (1.0 / critical_k)
    )
    intercept = math.log(RULER_ATMOSPHERIC_PRESSURE_BAR) + slope / boiling_k
    saturation_temp = slope / (intercept - math.log(pressure_absolute)) - 273.15
    saturation_temp = min(max(saturation_temp, minimum_temp), maximum_temp)
  else:
    saturation_temp = min(max(value, minimum_temp), maximum_temp)
    pressure_absolute = _ruler_pressure_abs(refrigerant, saturation_temp)
    pressure_gauge = pressure_absolute - RULER_ATMOSPHERIC_PRESSURE_BAR

  result = {
    "ok": True,
    "code": code,
    "name": refrigerant["name"],
    "type": refrigerant["type"],
    "boiling_point_c": refrigerant["bp"],
    "critical_temp_c": refrigerant["tc"],
    "critical_pressure_bar": refrigerant["pc"],
    "pressure_gauge_bar": round(pressure_gauge, 2),
    "pressure_absolute_bar": round(pressure_absolute, 2),
    "temperature_c": round(saturation_temp, 1),
    "minimum_pressure_bar": round(minimum_pressure, 2),
    "maximum_pressure_bar": round(maximum_pressure, 2),
    "minimum_temperature_c": round(minimum_temp, 1),
    "maximum_temperature_c": round(maximum_temp, 1),
    "zone": (
      "Низкотемпературное кипение" if saturation_temp <= -30 else
      "Испарение бытового холодильника" if saturation_temp <= -10 else
      "Околонулевая зона / кондиционирование" if saturation_temp <= 10 else
      "Конденсация / тёплая сторона" if saturation_temp <= 45 else
      "Высокая температура конденсации"
    ),
    "source_note": "Приближённая линия насыщения по нормальной температуре кипения и критической точке."
  }
  if include_options:
    result["refrigerants"] = REFRIGERANT_RULER_DATA
  return result

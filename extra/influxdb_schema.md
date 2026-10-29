### Measurement: `Activity Minutes`

| Field Key | Field Type |
| --- | --- |
| `minutesFairlyActive` | integer |
| `minutesLightlyActive` | integer |
| `minutesSedentary` | integer |
| `minutesVeryActive` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Activity Records`

| Field Key | Field Type |
| --- | --- |
| `ActiveDuration` | integer |
| `AverageHeartRate` | integer |
| `calories` | integer |
| `distance` | float |
| `duration` | integer |
| `steps` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `ActivityName` | string |

---

### Measurement: `BreathingRate`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `DeviceBatteryLevel`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

---

### Measurement: `GPS`

| Field Key | Field Type |
| --- | --- |
| `altitude` | float |
| `distance` | float |
| `heart_rate` | integer |
| `lat` | float |
| `lon` | float |
| `speed_kph` | float |

| Tag Key | Tag Type |
| --- | --- |
| `ActivityID` | string |

---

### Measurement: `HR zones`

| Field Key | Field Type |
| --- | --- |
| `Cardio` | integer |
| `Fat Burn` | integer |
| `Normal` | integer |
| `Peak` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HRV`

| Field Key | Field Type |
| --- | --- |
| `dailyRmssd` | float |
| `deepRmssd` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HeartRate_Intraday`

| Field Key | Field Type |
| --- | --- |
| `value` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `RestingHR`

| Field Key | Field Type |
| --- | --- |
| `value` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `SPO2`

| Field Key | Field Type |
| --- | --- |
| `avg` | float |
| `max` | float |
| `min` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `SPO2_Intraday`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Skin Temperature Variation`

| Field Key | Field Type |
| --- | --- |
| `RelativeValue` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Sleep Levels`

| Field Key | Field Type |
| --- | --- |
| `duration_seconds` | integer |
| `level` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |
| `isMainSleep` | string |

---

### Measurement: `Sleep Summary`

| Field Key | Field Type |
| --- | --- |
| `efficiency` | integer |
| `minutesAfterWakeup` | integer |
| `minutesAsleep` | integer |
| `minutesAwake` | integer |
| `minutesDeep` | integer |
| `minutesInBed` | integer |
| `minutesLight` | integer |
| `minutesREM` | integer |
| `minutesToFallAsleep` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |
| `isMainSleep` | string |

---

### Measurement: `Steps_Intraday`

| Field Key | Field Type |
| --- | --- |
| `value` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Total Steps`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `bmi`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `calories`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `distance`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `weight`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

## Optional measurements (Google Health API)

Written only when the matching value is listed in `EXTRA_FETCH_SELECTION` (see [extra/google-migration.md](google-migration.md)). `active_minutes` adds the lightly, fairly and very active fields of `Activity Minutes`, and `exercise_gps` writes the `GPS` measurement.

---

### Measurement: `Active Calories`

Enabled by `EXTRA_FETCH_SELECTION=active_calories`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `ActivityLevel_Intraday`

Enabled by `EXTRA_FETCH_SELECTION=activity_level`

| Field Key | Field Type |
| --- | --- |
| `level` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `BreathingRate_Sleep`

Enabled by `EXTRA_FETCH_SELECTION=breathing_sleep_stages`

| Field Key | Field Type |
| --- | --- |
| `deep` | float |
| `deep_snr` | float |
| `deep_stddev` | float |
| `full` | float |
| `full_snr` | float |
| `full_stddev` | float |
| `light` | float |
| `light_snr` | float |
| `light_stddev` | float |
| `rem` | float |
| `rem_snr` | float |
| `rem_stddev` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HR zone calories`

Enabled by `EXTRA_FETCH_SELECTION=hr_zone_time`

| Field Key | Field Type |
| --- | --- |
| `Light` | float |
| `Moderate` | float |
| `Peak` | float |
| `Vigorous` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HR zone limits`

Enabled by `EXTRA_FETCH_SELECTION=hr_zone_time`

| Field Key | Field Type |
| --- | --- |
| `Light_max` | integer |
| `Light_min` | integer |
| `Moderate_max` | integer |
| `Moderate_min` | integer |
| `Peak_max` | integer |
| `Peak_min` | integer |
| `Vigorous_max` | integer |
| `Vigorous_min` | integer |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HR zone time`

Enabled by `EXTRA_FETCH_SELECTION=hr_zone_time`

| Field Key | Field Type |
| --- | --- |
| `Light` | float |
| `Moderate` | float |
| `Peak` | float |
| `Vigorous` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `HRV_Intraday`

Enabled by `EXTRA_FETCH_SELECTION=hrv_intraday`

| Field Key | Field Type |
| --- | --- |
| `highFrequencyPower` | float |
| `lowFrequencyPower` | float |
| `rmssd` | float |
| `sdnn` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Hydration`

Enabled by `EXTRA_FETCH_SELECTION=hydration`

| Field Key | Field Type |
| --- | --- |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Nutrition`

Enabled by `EXTRA_FETCH_SELECTION=nutrition`

| Field Key | Field Type |
| --- | --- |
| `calories` | float |
| `caloriesFromFat` | float |
| `carbs_g` | float |
| `fat_g` | float |
| `<nutrient>_g` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `Swim`

Enabled by `EXTRA_FETCH_SELECTION=swim`

| Field Key | Field Type |
| --- | --- |
| `lengths` | integer |
| `strokes` | integer |
| `swimSeconds` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |

---

### Measurement: `VO2 Max`

Enabled by `EXTRA_FETCH_SELECTION=vo2max`

| Field Key | Field Type |
| --- | --- |
| `cardioFitnessLevel` | string |
| `covariance` | float |
| `estimated` | boolean |
| `measurementMethod` | string |
| `value` | float |

| Tag Key | Tag Type |
| --- | --- |
| `Device` | string |
| `Type` | string |

---

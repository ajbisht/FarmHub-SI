import re
from pathlib import Path

p = Path(r"C:\Users\ajay_bisht\RasberryPI\agent\llm_client.py")
text = p.read_text(encoding="utf-8")

# Replace the fallback reasoning strings directly using regex
text = re.sub(
    r'reasoning="Water reservoir is LOW\. Irrigation paused to prevent pump damage\."',
    'reasoning="Water tank is low. Holding off on watering until refilled."',
    text,
)

text = re.sub(
    r'reasoning=f"Soil moisture is \{moisture:\.1f\}%, but rain is forecasted \(\{weather\.rain_probability_pct\}% chance\)\. Conserving water\."',
    'reasoning=f"Rain expected soon ({weather.rain_probability_pct}% chance). Saving water today."',
    text,
)

text = re.sub(
    r'reasoning=f"Soil moisture is dry \(\{moisture:\.1f\}% < target 45%\)\. Irrigating 5 tomato plants for 30s\."',
    'reasoning=f"Soil dipped to {moisture:.0f}%. Clear skies, giving plants a 30s drink now."',
    text,
)

text = re.sub(
    r'reasoning=f"Soil moisture is optimal \(\{moisture:\.1f\}%\)\. No additional water needed\."',
    'reasoning=f"Soil is healthy and moist at {moisture:.0f}%. Plants are happy."',
    text,
)

text = re.sub(
    r'model_name="Local Agronomy Engine \(Offline\)"',
    'model_name="Field Agronomist (Offline)"',
    text,
)

p.write_text(text, encoding="utf-8")
print("Successfully updated llm_client.py fallback via file script!")

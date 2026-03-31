import xml.etree.ElementTree as ET

# Parse baseline tripinfo file
baseline_file = "/Users/mizmorchang/Desktop/newest/AgentSUMO/experiments_ceus/output/gangnam_output/simulations/gangnam_station.net_tripinfo_baseline.xml"
tree_baseline = ET.parse(baseline_file)
root_baseline = tree_baseline.getroot()

# Extract all trip durations from baseline
baseline_durations = []
for tripinfo in root_baseline.findall('tripinfo'):
    duration = float(tripinfo.get('duration'))
    baseline_durations.append(duration)

# Parse Webster (tls_adapt) tripinfo file
webster_file = "/Users/mizmorchang/Desktop/newest/AgentSUMO/experiments_ceus/output/gangnam_output/simulations/gangnam_station.net_tripinfo_tls_adapt.xml"
tree_webster = ET.parse(webster_file)
root_webster = tree_webster.getroot()

# Extract all trip durations from Webster
webster_durations = []
for tripinfo in root_webster.findall('tripinfo'):
    duration = float(tripinfo.get('duration'))
    webster_durations.append(duration)

# Calculate average trip durations
avg_baseline = sum(baseline_durations) / len(baseline_durations)
avg_webster = sum(webster_durations) / len(webster_durations)

# Calculate percentage reduction
percentage_reduction = ((avg_baseline - avg_webster) / avg_baseline) * 100

print(f"Baseline - Number of trips: {len(baseline_durations)}")
print(f"Baseline - Average trip duration: {avg_baseline:.2f} seconds")
print(f"\nWebster - Number of trips: {len(webster_durations)}")
print(f"Webster - Average trip duration: {avg_webster:.2f} seconds")
print(f"\nPercentage reduction: {percentage_reduction:.2f}%")

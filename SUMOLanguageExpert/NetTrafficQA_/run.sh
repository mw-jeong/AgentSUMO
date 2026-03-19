
for task in "feature_retrieval" "pathfinding" "network_comprehension"; do
    for baseline in "codegen" "adj" "raw"; do
        python run_experiment.py --task QAdataset/$task --baseline $baseline --network all --n 10
    done
done
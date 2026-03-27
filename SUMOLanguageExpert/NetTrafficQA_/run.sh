
# for network in "grid_11x11" "random"; do
#     python run_preprocess.py --net_file data/network/$network.net.xml
#     python generate_qa.py --network $network --n 10
# done

for task in "feature_retrieval" "pathfinding" "network_comprehension"; do
    for baseline in "codegen" "adj" "raw"; do
        python run_experiment.py --task QAdataset/$task --baseline $baseline --network all --n 10
    done
done

python evaluate.py --task QAdataset

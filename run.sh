echo "setting up environment"
bash set_up.sh
echo "clearing logs"
rm -rf logs/*
echo "running experiments"
echo "bottles:"
python main.py --config ./config/bottles.txt

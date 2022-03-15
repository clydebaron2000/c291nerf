echo "clearing logs"
rm -rf logs/*
echo "running experiments"
echo "bottles:"
python main.py --config ./configs/bottles.txt

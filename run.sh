echo "clearing logs"
python -c "import torch; torch.cuda.empty_cache()"
rm -rf logs/bottles_test*
echo "running experiments"
echo "bottles:"
python main.py --config ./configs/bottles.txt

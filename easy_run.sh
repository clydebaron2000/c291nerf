echo "setting up environment"
bash set_up.sh
echo "running experiments"
echo "bottles:"
python main.py --config ./config/bottles.txt
echo "lego:"
python main.py --config ./config/lego.txt

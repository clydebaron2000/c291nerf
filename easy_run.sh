echo "setting up environment"
bash set_up.sh
echo "running experiments"
echo "bottles:"
python run_nerf.py config_bottles.txt
echo "lego:"
python run_nerf.py config_lego.txt

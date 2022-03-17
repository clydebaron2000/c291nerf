# C291 Final Project NeRF Implementaion

Implements a NeRF inspired by the original [NeRF](https://github.com/bmild/nerf) and its faithful PyTorch implementation [NeRF-pytorch](https://github.com/yenchenlin/nerf-pytorch).

# usage
If running in a linux VM or a remote computer with linux, after cloning the repo, run
```bash
bash ./setup/set_up.sh
```
then simply run `python main.py --config ./configs/<EXPERIMENT NAME>` or modify `run.sh`.

# results 

bottles.txt:
![bottles](https://github.com/clydebaron2000/c291nerf/tree/main/logs/bottles_test/bottles_test_spiral_100000_rgb.mp4)

lego.txt:
![lego](https://github.com/clydebaron2000/c291nerf/tree/main/logs/lego_test/lego_test_spiral_100000_rgb.mp4)

# contributors 
- created by [clydebaron2000](https://github.com/clydebaron2000)
- consulted with [jonzamora](https://github.com/jonzamora)

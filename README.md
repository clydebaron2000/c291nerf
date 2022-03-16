# c291 final project NeRF implementaion

Implements a NeRF inspired by the original [NeRF](https://github.com/bmild/nerf) and its faithful PyTorch implementation [NeRF-pytorch](https://github.com/yenchenlin/nerf-pytorch).

# usage
If running in a linux VM or a remote computer with linux, run
```bash
bash ./setup/set_up.sh
```
then simply run `python main.py --config ./configs/<EXPERIMENT NAME>` or modify `run.sh`.

Additionally, if you want to instantly run the code with default configs in `configs`, copy-paste the contents of `clone_and_run.sh` into your terminal.

# results 

bottles.txt:
![bottles](https://github.com/clydebaron2000/c291nerf/tree/main/logs/bottles_test/bottles_test_spiral_100000_rgb.mp4)

lego.txt:
![lego](https://github.com/clydebaron2000/c291nerf/tree/main/logs/lego_test/lego_test_spiral_100000_rgb.mp4)

# contributors 
- created by [clydebaron2000](https://github.com/clydebaron2000)
- consulted with [jonzamora](https://github.com/jonzamora)

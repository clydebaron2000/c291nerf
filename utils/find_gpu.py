########################################################################################################################
#  modified gist from https://gist.github.com/afspies/7e211b83ca5a8902849b05ded9a10696
########################################################################################################################
# TODO: un-used, possibly delete?

import os
from subprocess import check_output


# This function should be called after all imports,
# in case you are setting CUDA_AVAILABLE_DEVICES elsewhere
def assign_free_gpus(threshold_vram_usage=1_000_000, max_gpus=2):
    """Assigns free gpus to the current process via the CUDA_AVAILABLE_DEVICES env variable
    Args:
        threshold_vram_usage (int, optional): A GPU is considered free if the vram usage is below the threshold
                                            Defaults to 1500 (MiB).
        max_gpus (int, optional): Max GPUs is the maximum number of gpus to assign.
                                Defaults to 2.
    """
    # Get the list of GPUs via nvidia-smi
    smi_query_result = check_output('nvidia-smi -q -d Memory | grep -A4 GPU', shell=True)
    # Extract the usage information
    gpu_info = smi_query_result.decode('utf-8').split('\n')
    gpu_info = list(filter(lambda info: 'Used' in info, gpu_info))
    gpu_info = [int(x.split(':')[1].replace('MiB', '').strip()) for x in gpu_info] # Remove garbage
    gpu_info = gpu_info[:min(max_gpus, len(gpu_info))] # Limit to max_gpus
    # Assign free gpus to the current process
    gpus_to_use = ','.join([str(i) for i, x in enumerate(gpu_info) if x < threshold_vram_usage])
    # print(f'Using GPU(s): {gpus_to_use}' if gpus_to_use else 'No free GPUs found')
    if not gpus_to_use:
        print('No free GPUs found')
        return "cpu"
#     os.environ['CUDA_VISIBLE_DEVICES'] = gpus_to_use
    return f'cuda:{gpus_to_use[0]}'  
if __name__ == '__main__':
    assign_free_gpus()

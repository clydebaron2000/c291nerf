echo "installing conda"
apt-get install conda
echo "setting up environment"
conda env create -f environment.yml
echo "downloading sample dataset"
bash download_example_data.sh
echo "unzipping zip files"
echo "\t downloading unzip"
apt-get install unzip
echo "\t unzipping data/zip fiels"
unzip data/zip/*.zip -d data/
echo "set-up successful"
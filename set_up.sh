echo "installing pip"
apt-get install pip
echo "setting up environment"
pip install -r requirements.txt
echo "\t downloading unzip"
apt-get install unzip
echo "\t installing wget"
apt-get install wget
echo "downloading official datasets"
bash ./setup/download_official_data.sh
echo "unzipping zip files"
echo "\t unzipping data/zip fiels"
unzip data/zip/*.zip -d data/
echo "set-up successful"
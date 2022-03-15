echo "installing pip"
apt-get install pip
echo "setting up environment"
# needed for sklearn
apt-get install piplibsm6
apt-get install libxext6
pip install -r ./setup/requirements.txt
echo "\t downloading unzip"
apt-get install unzip
echo "\t installing wget"
apt-get install wget
mkdir -p data
echo "downloading official datasets"
bash ./setup/download_official_data.sh
echo "downloading class database"
echo "\t installing gdown"
apt-get install gdown
gdown --id 107f10G02el4EgIE_4852NH9WhdkL1jbN -O ./data/
echo "\t unzipping ./data/bottles.zip"
unzip ./data/bottles.zip -d ./data/
rm -rf ./data/__*
echo "set-up successful"

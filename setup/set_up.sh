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
echo "downloading class database"
echo "\t installing gdown"
apt-get install gdown
gdown --id 107f10G02el4EgIE_4852NH9WhdkL1jbN -O ./data/.
echo "\t unzipping ./data/bottles.zip"
unzip ./data/bottles.zip -d ./data/
echo "set-up successful"
import os

def list_files(directory):
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

if __name__ == "__main__":
    directory = "/Users/kanavkahol/work/data_2_phone/preprocessing/column_summaries"
    files = list_files(directory)
    print("Files in directory:", files)

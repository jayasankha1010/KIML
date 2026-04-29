def preprocess_mydata(path):
    import pandas as pd

    df = pd.read_csv(path, sep="\t", header=0, index_col=0)

    return df


def test_preprocess_labels(path) -> set:
    import pandas as pd

    return set(pd.read_csv(path, sep="\t", header=None, names=["0"])["0"].tolist())


def preprocess_mydata_expression(path):
    import pandas as pd

    df = pd.read_csv(path, sep=" ", header=None, index_col=0)
    df = df[~df.index.duplicated(keep='first')]

    return df

def preprocess_mydata_expression_scaled(path, scale_factor=0.8):
    import pandas as pd

    df = pd.read_csv(path, sep=" ", header=None, index_col=0)
    df = df[~df.index.duplicated(keep='first')]

    # Scale all values in the DataFrame by the scale_factor
    df = df * scale_factor * 2

    return df

def scale_80_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.8)

def scale_60_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.6)

def scale_40_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.4)

def scale_20_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.2)

def scale_10_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.1)

def scale_90_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.9)

def scale_50_percent(path):
    return preprocess_mydata_expression_scaled(path, scale_factor=0.5)

from datetime import datetime
import json
import pandas as pd


def read_csv(file):
    # reads csv file and returns Pandas dataframe
    return pd.read_csv(file)


class RunTracker:
    """
    This class will be responsible for tracking model runs. It calculates the desired metadata based on a model's
    inputs, outputs, and other run-specific features, before uploading them to Ersilia's Splunk dashboard.

    NOTE: Currently, the Splunk connection is not set up. For now, we will print tracking results to the console.
    """

    def __init__(self):
        self.time_start = None

    # function to be called before model is run
    def start_tracking(self):
        self.time_start = datetime.now()

    def sample_df(self, df, num_rows, num_cols):
        """
        Returns a sample of the dataframe, with the specified number of rows and columns.
        """
        return df.sample(num_rows, axis=0).sample(num_cols, axis=1)

    def stats(self, result):
        dat = read_csv(result)

        # drop first two columns (key, input)
        dat = dat.drop(["key", "input"], axis=1)

        # calculate and print statistics
        stats = {}
        for column in dat:
            column_stats = {}
            column_stats['mean'] = dat[column].mean()
            if len(dat[column].mode()) == 1:
                column_stats['mode'] = dat[column].mode()
            else:
                column_stats['mode'] = None
            column_stats['min'] = dat[column].min()
            column_stats['max'] = dat[column].max()
            column_stats['std'] = dat[column].std()

            stats[column] = column_stats

        return stats

    def get_file_sizes(self, input_df, output_df):
        input_size = input_df.memory_usage(deep=True).sum() / 1024
        output_size = output_df.memory_usage(deep=True).sum() / 1024

        input_avg_row_size = input_size / len(input_df)
        output_avg_row_size = output_size / len(output_df)

        return {
            "input_size": input_size,
            "output_size": output_size,
            "avg_input_size": input_avg_row_size,
            "avg_output_size": output_avg_row_size,
        }

    def track(self, input, result, meta):
        """
        Tracks the results after a model run.
        """
        json_dict = {}
        input_dataframe = read_csv(input)
        result_dataframe = read_csv(result)

        json_dict["input_dataframe"] = input_dataframe.to_dict()
        json_dict["result_dataframe"] = result_dataframe.to_dict()

        json_dict["meta"] = meta

        model_id = meta["metadata"].get("Identifier", "Unknown")
        json_dict["model_id"] = model_id

        time = datetime.now() - self.time_start
        json_dict["time_taken"] = str(time)

        # checking for mismatched types
        nan_count = result_dataframe.isna().sum()
        json_dict["nan_count"] = nan_count.to_dict()

        json_dict["check_types"] = self.check_types(result_dataframe, meta["metadata"])

        json_dict["stats"] = self.stats(result)

        json_dict['file_sizes'] = self.get_file_sizes(input_dataframe, result_dataframe)

        json_object = json.dumps(json_dict, indent=4)
        print("\nJSON Dictionary:\n", json_object)

        # log results to console
        with open("../cli/commands/current_session.txt", "a") as f:
            # write the print statements to a file
            f.write(json_object)

    def log_to_console(self, data):
        print(f"\n{json.dumps(data)}\n")

    def read_json(self, result):
        data = json.load(result)
        self.log_to_console(result)
        return data

    def check_types(self, resultDf, metadata):
        typeDict = {"float64": "Float", "int64": "Int"}
        count = 0

        # ignore key and input columns
        dtypesLst = resultDf.loc[:, ~resultDf.columns.isin(["key", "input"])].dtypes

        for i in dtypesLst:
            if typeDict[str(i)] != metadata["Output Type"][0]:
                count += 1

        if len(dtypesLst) > 1 and metadata["Output Shape"] != "List":
            print("Not right shape. Expected List but got Single")
            correct_shape = False
        elif len(dtypesLst) == 1 and metadata["Output Shape"] != "Single":
            print("Not right shape. Expected Single but got List")
            correct_shape = False
        else:
            print("Output is correct shape.")
            correct_shape = True

        print("Output has", count, "mismatched types.\n")

        return {
            "mismatched_types": count,
            "correct_shape": correct_shape
        }

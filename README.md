# General Neuroimaging Processing Repository

The neuro-utils repository contains the master script `pipeline.py`. With this command, you can modularly run different elements of the processing pipeline. The pipeline assumes a specific kind of file and folder organization (specified below) and works best with BIDS-type datasets (outputs are, as a standard, mostly written in a BIDS-type format into the 'derivatives' folder of the project you're working on).

## How to run the pipeline from the command line
A smart way to call the pipeline is by using the following command on Tux17:
```nohup python -u pipeline.py -p ... -m ... > ~/projects/pipeline_logs/DATE_pipeline_MODULE.log & disown```

This way, the output of the master command is piped into a log folder, and the full pipeline is not aborted when you are disconnected from the terminal.

```
usage: pipeline.py 
[-h] -p PROJECT -m MODULES [MODULES ...] 
[-s SUBJECT [SUBJECT ...]]
[-n SESSION [SESSION ...]] 
[-r RUN [RUN ...]]
[-x [EXTRA_ARGS ...]]

Master pipeline script for neuroimaging data processing.

options:
  -h, --help            show this help message and exit
  -p PROJECT, --project PROJECT
                        Project name
  -m MODULES [MODULES ...], --modules MODULES [MODULES ...]
                        Space-separated list of modules to run
  -s SUBJECT [SUBJECT ...], --subject SUBJECT [SUBJECT ...]
                        Space-separated list of subject IDs (optional)
  -n SESSION [SESSION ...], --session SESSION [SESSION ...]
                        Space-separated list of session numbers (optional)
  -r RUN [RUN ...], --run RUN [RUN ...]
                        Space-separated list of run numbers (optional)
  -x [EXTRA_ARGS ...], --extra_args [EXTRA_ARGS ...]
                        Extra args for module scripts
```

## How the pipeline works
Into `pipeline.py`, you input the name of a project you're working on. The pipeline subsequently looks into `/home/USER/projects/PROJECT`, to a file called `configs/dataset.yaml`. This file contains information about the dataset, subjects, derivatives folder, etc. The pipeline loads this `yaml` to create a project-specific log dir. It then loops over the modules you have provided, and executes the modules individually. 

As extra options to the pipeline command, you may specify subjects, sessions, or runs that you want to process (in case you do not want to process everything at the same time). In case you don't specify these options, the pipeline will assume you want to process the entire dataset and feed this into the individual modules. 

Each module (indicated with a number, which corresponds to a processing step; specified in the`pipeline.py` header) has its corresponding script file in `neuro-utils/scripts`. These scripts are run sequentially. In the `pipeline.py` script, each module is called with the following arguments:
```
parser.add_argument("-c", "--config", required=True, help="Path to project YAML config file")

parser.add_argument("-s", "--subjects", nargs="+", help="Space-separated list of subject IDs (optional)")

parser.add_argument("-n", "--sessions", nargs="+", help="Space-separated list of session numbers (optional)")

parser.add_argument("-r", "--runs", nargs="+", help="Space-separated list of run numbers (optional)")
```
If you want to include a new module in the pipeline, you should be sure that this logic is accepted in the module-specific script.

## Logs
There are three types of logs created during the processing:
- *Master pipeline log file*: This is an overarching log file for the entire pipeline. It just contains basic output for different processing modules (e.g.; **Module X started, finished at time X**), and you can choose a custom location for this (based on where you pipe the output of the master pipeline command).
- *Module-specific log file:* These log files are created in the folder `~/projects/PROJECT/logs/`. They contain all the detailed output created during the individual processing modules.
- *Overall failure-success log file*: This log file is created in `~/projects/pipeline_summary.csv`, and only includes basic information about each module you ran (e.g. time, arguments), and whether it finished successfully or not.

## Crashes, working directories, etc.
Generally, the modules are programmed such that they process everything on a scratch directory on Tux17, as this is faster than loading from the mounted FMG research drive [[How to mount FMG-research on Tux17]]. This scratch folder is located in `~/projects/scratch`, with an individual folder for each project and each processing module. This is a working directory where the files are stored/processed until the module is finished, after which the outputs are put back in the `derivatives` folder. This happens at the start of each module script. At the end, the working directory is removed, but if the module crashes the files are still there. In that case, you might have to remove it yourself.

If something goes wrong with the pipeline, you should kill the master command.
- `ps -ef | grep pipeline.py` to get the pid
- `pstree -p PID` to get the tree of processes
- `pkill -TERM -P PID` to kill the tree

When you run a complex pipeline (e.g. in Docker), the processing container may keep running even if you kill the main pipeline command. To kill the docker container;
- `docker ps`
- `docker stop <container_id>`
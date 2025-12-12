# Route-Optimization-ISPA
Route-Optimization-ISPA
# Multi-Criteria Route Optimization using GIS and MCDM Methods

## Overview

This repository contains the complete MATLAB codebase for the research paper titled: **"Iterative Score Propagation Algorithm (ISPA): A GNN-Inspired Framework for Multi-Criteria Route Design with Engineering Applications,"** published open access in the **ISPRS International Journal of Geo-Information (IJGI)**. The project presents an integrated methodological framework for optimal route selection by synergizing Geographic Information Systems (GIS) with Multi-Criteria Decision Making (MCDM) techniques. 

The primary contribution of this work is a comparative analysis of four distinct suitability scoring methods:

**Suitability Scoring Methods:** 
1. **AHP** (Analytic Hierarchy Process) as a Weighted Linear Combination (WLC) 
2. **TOPSIS** (Technique for Order of Preference by Similarity to Ideal Solution) 
3. **VIKOR** (VlseKriterijumska Optimizacija I Kompromisno Resenje) 
4. **ISPA** (Iterative Score Propagation Algorithm), a novel GNN-inspired method for spatial contextualization. 

This codebase is provided to ensure the **transparency**, **reproducibility**, and **extensibility** of **this research**.

---

## Project Structure

```
.
├── generate_spatial_parameters.m  # Module 1: Generates criteria parameters from base data
├── road_project_main.m     # Module 2: Performs the MCDM analysis and route optimization
├── input_data/
│   └── sample_nodes.xlsx            # Sample input file (INPUT04_20.xlsx) with node coordinates (Easting, Northing, Elevation)
└── README.md                        # This file
```

---

## How to Use

This project requires **MATLAB R2022a** or newer, with the following toolboxes installed:
*   Statistics and Machine Learning Toolbox
*   Mapping Toolbox (optional, for advanced visualizations)

### Step 1: Parameter Generation

This step creates a realistic decision environment from a simple list of node coordinates.

1.  **Prepare Your Data:** Create an Excel file (`INPUT04_20.xlsx`) containing your node points. It must include columns for Easting, Northing, and Elevation. A sample file is provided in the `input_data` folder. Place this file in your MATLAB working directory.

2.  **Run the Script:** Open MATLAB and run the `generate_realistic_parameters.m` script.
    ```matlab
    >> generate_realistic_parameters
    ```

3.  **Interactive Process:** The script will guide you through an interactive process:
    *   It will first ask you to select your input node file (e.g., `sample_nodes.xlsx`).
    *   It will then automatically calculate the `Slope (%)` parameter.
    *   Subsequently, it will open a 2D map and ask you to define other criteria layers (**Existing Roads**, **Settlement Areas**, **Sensitive Areas**) either by loading data from external files or by interactively drawing them on the map.
    *   You can choose to skip any of these layers.

4.  **Output:** This script will generate a new Excel file named `parametreler_[your_input_file_name].xlsx`. This file contains the original coordinates plus the four generated criteria columns (`Egim_Percent`, `MevcutYolKullanimi`, `YerlesimMaliyeti`, `HassasAlanMaliyeti`) and is the primary input for the next stage.

### Step 2: Route Optimization and Analysis

This is the main module that performs the multi-method analysis and generates the final results.

1.  **Run the Script:** In MATLAB, run the `road_project_main.m` script.
    ```matlab
    >> road_project_main
    ```

2.  **Interactive Selections:** The script will present a series of dialog boxes for you to configure the analysis:
    *   **Input File:** Select the parameter file generated in Step 1 (e.g., `parametreler_sample_nodes.xlsx`).
    *   **Analysis Methods:** Choose which of the four methods (AHP, TOPSIS, VIKOR, ISPA/GNN) you want to run.
    *   **Weighting Method:** Select either **AHP** (for subjective, expert-driven weights) or **Entropy** (for objective, data-driven weights).
    *   **Criteria Direction:** Define each criterion as a **Benefit** (higher value is better) or a **Cost** (lower value is better).
    *   **Start/End Nodes:** Select the start and end nodes for the route optimization, either from a 2D map or by manually entering their row indices.

3.  **Output:** The script will automatically generate and save all results in a new folder named `results_[your_input_file_name]_[...analysis_details...]`. This folder will contain:
    *   **`Optimizasyon_Raporu.xlsx`:** A multi-sheet Excel file with all numerical results, including node scores and the comparative analysis table for the generated routes.
    *   **`Skor_Haritalari_2D.png` & `_3D.png`:** Visualizations of the suitability maps produced by each method.
    *   **`Guzergahlar_2D_Harita.png` & `_3D_Modeli.png`:** Professional, publication-quality figures comparing the final optimal routes.

---

## Citation

If you use this code in your research, please cite our paper:

Pehlivan, H. Iterative Score Propagation Algorithm (ISPA): A GNN-Inspired Framework for Multi-Criteria Route Design with Engineering Applications. *ISPRS Int. J. Geo-Inf.* 2025, *14*(12), 484. https://doi.org/10.3390/ijgi14120484

### BibTeX Citation 
@article{Pehlivan2025ISPA, 
title = {Iterative Score Propagation Algorithm (ISPA): A GNN-Inspired Framework for Multi-Criteria Route Design with Engineering Applications}, 
author = {Pehlivan, Hüseyin}, 
journal = {ISPRS International Journal of Geo-Information}, 
year = {2025}, 
volume = {14}, 
number = {12}, 
pages = {484}, 
doi = {10.3390/ijgi14120484} 
}

```

## License

This project is licensed under the MIT License - see the `LICENSE.md` file for details (optional, but good practice).

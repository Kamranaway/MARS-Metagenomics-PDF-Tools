import math
import argparse
import pickle
import random
from os import listdir, path
import sys

from matplotlib import colors
import read_data as rd
import numpy as np
import composition_stats as cs
import numpy as np
from scipy import stats as scistats
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
# import rpy2.robjects as robjects
import alphas as alphas
import taxonomy as tax
import betas as betas

seed = 0

def generate_beta_report(output_name, all_read_data_names, all_read_data):
    output = PdfPages(output_name + ".beta_report.pdf")
    
    all_fungi_ratios = []
    all_fungi_counts = []
    all_phylum_scores = []
    all_genus_scores = []
    all_read_sets = []
    all_abundance_estimates = {}
    for idx, read_data in enumerate(all_read_data):
        current_name = all_read_data_names[idx]
        tax_count_dict = read_data.get_tax_count_dict()
        tax_dict = read_data.get_tax_dict()
        
        species_level_estimates = tax_count_dict["genus"]
        read_ids = [read.get_assignment() for read in read_data.reads.values()]
        read_ids_genus = []
        for read_id in read_ids:
            new_id = tax_dict.id_2_level_id(read_id, "genus")
            read_ids_genus.append(new_id)
        all_read_sets.append(read_ids_genus)
    

        all_abundance_estimates[current_name] = species_level_estimates
        estimate_list = list(species_level_estimates.values())  
        count_sum = sum(estimate_list)
        richness = len(estimate_list)
        chao1 = alphas.chao1(estimate_list)
        shannons_alpha = alphas.shannons_alpha(estimate_list)
        bp = alphas.berger_parkers_alpha(estimate_list)
        simp = alphas.simpsons_alpha(estimate_list)
        in_simp = alphas.inverse_simpsons_alpha(estimate_list)
        
        evenness = shannons_alpha / math.log(richness)
        
        tax_table = tax_count_dict
        fungi_count = 0
        
        if "kingdom" in tax_table:
            if "Fungi" in tax_table["kingdom"]:
                fungi_count = tax_table["kingdom"]["Fungi"]
                
        fungus_species_ratio = 0
        if fungi_count != 0:
            fungus_species_ratio = (fungi_count / (count_sum - fungi_count))  
            
        all_fungi_ratios.append(fungus_species_ratio)
        all_fungi_counts.append(fungi_count)
        
        # genus level z-scores
        z_scores = scistats.zscore(list(tax_table["genus"].values()))
        labels = list(tax_table["genus"].keys())
        z_dict = {}
        for i in range(len(labels)):
            z_dict[labels[i]] = z_scores[i]
        all_genus_scores.append(z_dict)
            
        # phylum level z-scores
        z_scores = scistats.zscore(list(tax_table["phylum"].values()))
        labels = list(tax_table["phylum"].keys())
        z_dict = {}
        for i in range(len(labels)):
            z_dict[labels[i]] = z_scores[i]
        all_phylum_scores.append(z_dict)
   
    # Collect all phylums 
    all_phylums = {}
    for phylum_scores in all_phylum_scores:
        for phylum in phylum_scores.keys():
            if phylum not in all_phylums:
                all_phylums[phylum] = 1
                
    #collect all genus
    all_genus = {}
    for genus_scores in all_genus_scores:
        for genus in genus_scores.keys():
            if genus not in all_genus:
                all_genus[genus] = 1
    

    # Insert 0 values for missing entries in the z-scores
    for phylum_scores in all_phylum_scores:
        for phylum in all_phylums.keys():
            if phylum not in phylum_scores:
                phylum_scores[phylum] = 0
                
    # Insert 0 values for missing entries in the z-scores
    for genus_scores in all_genus_scores:
        for genus in all_genus.keys():
            if genus not in genus_scores:
                genus_scores[genus] = 0
    
    # Collect all ids in the abundance estimates
    all_ids = {}
    for prefix in all_abundance_estimates:
        species_level_estimates = all_abundance_estimates[prefix]
        for id in species_level_estimates.keys():
            if id not in all_ids:
                all_ids[id] = 1

    # Insert 0 values for missing entries in the abundance estimates
    for prefix in all_abundance_estimates:
        species_level_estimates = all_abundance_estimates[prefix]
        for id in all_ids.keys():
            if id not in species_level_estimates:
                species_level_estimates[id] = 0
                
    all_unit_sets = all_read_data
    all_unit_names = all_read_data_names
    # Beta matrices
    bc_matrix = np.zeros((len(all_unit_sets), len(all_unit_sets)))
    jaccard_matrix = np.zeros((len(all_unit_sets), len(all_unit_sets)))
    city_block_matrix = np.zeros((len(all_unit_sets), len(all_unit_sets)))
    aitchison_matrix = np.zeros((len(all_unit_sets), len(all_unit_sets)))
    
    for current_name in all_unit_names:
        for other_name in all_unit_names:
            if current_name == other_name:
                bc_matrix[all_unit_names.index(current_name)][all_unit_names.index(other_name)] = 0 # same sample
                continue
            current_abundance_estimates = all_abundance_estimates[current_name]
            other_abundance_estimates = all_abundance_estimates[other_name]
            
            bc_matrix[all_unit_names.index(current_name)][all_unit_names.index(other_name)] = betas.bray_curtis_distance(current_abundance_estimates, other_abundance_estimates, all_ids)
            jaccard_matrix[all_unit_names.index(current_name)][all_unit_names.index(other_name)] = betas.jaccard_distance(current_abundance_estimates, other_abundance_estimates, all_ids)
            city_block_matrix[all_unit_names.index(current_name)][all_unit_names.index(other_name)] = betas.city_block_distance(current_abundance_estimates, other_abundance_estimates, all_ids)
            #aitchison_matrix[all_unit_names.index(current_name)][all_unit_names.index(other_name)] = betas.aitchison_distance(current_abundance_estimates, other_abundance_estimates, all_ids)
       

    # Phylum level heatmap comparison between samples
    data = []
    y_labels = []
    for phylum in all_phylums.keys():
        y_labels.append(phylum)
        row = []
        for prefix in all_unit_names:
            row.append(all_phylum_scores[all_unit_names.index(prefix)][phylum])
        data.append(row)
    x_labels = all_unit_names
    
    # Rarefaction curves
    curves_dict = {}
    for idx, read_data in enumerate(all_read_data):
        current_name = all_read_data_names[idx]
        
        filtered_reads = all_read_sets[idx]
            
        reads_processed = 0
        read_per_genus = {}
        read_per_otu = {}
        
        num_genus_rare = []
        num_otus_rare = []
        alphas_chao1_rare = []
        alphas_shannon_rare = []
        alphas_evenness_rare = []
        random.seed(0)
        
        while len(filtered_reads) > 0:
            index = random.choice(range(len(filtered_reads)))
            (id) = filtered_reads.pop(index)
            reads_processed += 1
            
            # Compute new values
            if id not in read_per_genus:
                read_per_genus[id] = 0
            # if unit not in read_per_otu:
            #     read_per_otu[unit] = 0
            
            read_per_genus[id] += 1
            #read_per_otu[unit] += 1

            
            # compute current number of species
            num_genus = 0
            for id in read_per_genus.keys():
                if read_per_genus[id] > 0:
                    num_genus += 1
            num_genus_rare.append(num_genus)
            
            # compute current number of otus
            # num_otus = 0
            # for unit in read_per_otu.keys():
            #     if read_per_otu[unit] > 0:
            #         num_otus += 1
            # num_otus_rare.append(num_otus)
            
                
            estimate_list = list(read_per_genus.values())  
            alphas_chao1_rare.append(alphas.chao1(estimate_list))
            if len(estimate_list) == 1:
                sa = 0
            else:
                sa = alphas.shannons_alpha(estimate_list)
            alphas_shannon_rare.append(sa)
            if math.log(num_genus) == 0:
                alphas_evenness_rare.append(0)
            else:
                alphas_evenness_rare.append( sa / math.log(num_genus))
        curves_dict[current_name] = {}
        curves_dict[current_name]["num_species"] = num_genus_rare
        curves_dict[current_name]["num_otus"] = num_otus_rare
        curves_dict[current_name]["chao1"] = alphas_chao1_rare
        curves_dict[current_name]["shannon"] = alphas_shannon_rare
        curves_dict[current_name]["evenness"] = alphas_evenness_rare
    
    # Plot phylum level heatmap
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    im = plots.imshow(data, aspect='auto', cmap='hot' , norm=colors.Normalize(vmin=min(z_scores), vmax=max(z_scores)))
    plots.set_title("Phylum Z-Scores")
    plots.set_xticks(np.arange(len(x_labels)), labels=x_labels, rotation=45, size='small')
    plots.set_yticks(np.arange(len(y_labels)), labels=y_labels) 
    plots.figure.colorbar(im)
    #plt.show()
    plt.tight_layout()
    output.savefig()
    plt.close()
    
    # Plot Bray-Curtis matrix heatmap
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    im = plots.imshow(bc_matrix, aspect='auto')
    plots.set_title("Bray-Curtis Distance")
    plots.set_xticks(np.arange(len(x_labels)), labels=x_labels, rotation=45, size='small')
    plots.set_yticks(np.arange(len(x_labels)), labels=x_labels, size='small')
    plots.figure.colorbar(im)
    mean = np.mean(bc_matrix)
    
    for i in range(len(bc_matrix)):
        for j in range(len(bc_matrix)):
            text = plots.text(j, i, bc_matrix[i, j], ha="center", va="center", color='white' if bc_matrix[i, j] < mean else 'black')
    
    plt.tight_layout()
    output.savefig()
    plt.close()
    
    # Plot Jaccard matrix heatmap
    # fig, plots = plt.subplots(1, 1)
    # fig.set_figwidth(12)
    # fig.set_figheight(8)
    # im = plots.imshow(jaccard_matrix, aspect='auto')
    # plots.set_title("Jaccard Distance")
    # plots.set_xticks(np.arange(len(x_labels)), labels=x_labels, rotation=45, size='small')
    # plots.set_yticks(np.arange(len(x_labels)), labels=x_labels, size='small')
    # plots.figure.colorbar(im)
    # mean = np.mean(jaccard_matrix)
    
    # for i in range(len(jaccard_matrix)):
    #     for j in range(len(jaccard_matrix)):
    #         text = plots.text(j, i, jaccard_matrix[i, j], ha="center", va="center", color='white' if jaccard_matrix[i, j] < mean else 'black')
    
    # plt.tight_layout()
    # output.savefig()
    
    # Plot City Block matrix heatmap
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    im = plots.imshow(city_block_matrix, aspect='auto')
    plots.set_title("City Block Distance")
    plots.set_xticks(np.arange(len(x_labels)), labels=x_labels, rotation=45, size='small')
    plots.set_yticks(np.arange(len(x_labels)), labels=x_labels, size='small')
    plots.figure.colorbar(im)
    mean = np.mean(city_block_matrix)
    
    for i in range(len(city_block_matrix)):
        for j in range(len(city_block_matrix)):
            text = plots.text(j, i, city_block_matrix[i, j], ha="center", va="center", color='white' if city_block_matrix[i, j] < mean else 'black')
    
    plt.tight_layout()
    output.savefig()
    
    # # Plot Aitchison matrix heatmap
    # fig, plots = plt.subplots(1, 1)
    # fig.set_figwidth(12)
    # fig.set_figheight(8)
    # im = plots.imshow(jaccard_matrix, aspect='auto')
    # plots.set_title("Aitchison Distance")
    # plots.set_xticks(np.arange(len(x_labels)), labels=x_labels, rotation=45, size='small')
    # plots.set_yticks(np.arange(len(x_labels)), labels=x_labels, size='small')
    # plots.figure.colorbar(im)
    # mean = np.mean(aitchison_matrix)
    
    # for i in range(len(aitchison_matrix)):
    #     for j in range(len(aitchison_matrix)):
    #         text = plots.text(j, i, aitchison_matrix[i, j], ha="center", va="center", color='white' if aitchison_matrix[i, j] < mean else 'black')
    
    # plt.tight_layout()
    # output.savefig()
    plt.close()
    
    # Plot rarefaction curves    
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    for name in curves_dict.keys():
        plots.plot(curves_dict[name]["num_species"], label=name)
    plots.set_title("Genus Count")
    #plots.xlabel("Reads Processed")
    plt.legend(loc='upper left')
    output.savefig()
    plt.close()
    
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    for name in curves_dict.keys():
        plots.plot(curves_dict[name]["chao1"], label=name)
    plots.set_title("Chao1")
    #plots.xlabel("Reads Processed")
    plt.legend(loc='upper left')
    output.savefig()
    plt.close()
    
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    for name in curves_dict.keys():
        plots.plot(curves_dict[name]["shannon"], label=name)
    plots.set_title("Shannon's Alpha")
    #plots.xlabel("Reads Processed")
    plt.legend(loc='upper left')
    output.savefig()
    plt.close()
    
    fig, plots = plt.subplots(1, 1)
    fig.set_figwidth(12)
    fig.set_figheight(8)
    for name in curves_dict.keys():
        plots.plot(curves_dict[name]["evenness"], label=name)
    plots.set_title("Evenness")
    #.xlabel("Reads Processed")
    plt.legend(loc='upper left')
    output.savefig()
    plt.close()
    
    print("Output written to", output._file.fh.name)
    output.close()      
   



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Beta Diversity", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-f", "--files", nargs='+', help="Files to compare")
    parser.add_argument("-s", "--seed", type=str, help="Seed for random number generator", default=0)
 
    args = parser.parse_args()
    config = vars(args)
    files = config["files"]
    seed = config["seed"]
    
    # if no files given
    if files == None:
        files = []
        dir_files = listdir("reads")
        for file in dir_files:
            if path.splitext(file)[1] != ".p":
                continue
            files.append(path.splitext(file)[0] + ".p")
       
        if file is None:
            sys.exit("No files found in reads ~/reads directory.") 
    
    output_prefix = ""
    all_read_data = []
    all_read_data_names = []
    
    for file in files:
        current_name = path.splitext(file)[0]
        output_prefix += current_name + "_"
        read_data = rd.ReadData()
        read_data.load_data(pickle.load(open("reads/" + file, "rb")))
        all_read_data.append(read_data)
        all_read_data_names.append(current_name)

    generate_beta_report( output_prefix, all_read_data_names, all_read_data)
    
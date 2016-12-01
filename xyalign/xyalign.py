# To-do list
# 1) Add ploidy estimation
# 		- need to add likelihood analyses (model fitting)
# 2) Compartmentalize all steps of analysis
# 		- Add flags to make each part of the pipeline optional
# 		- Allow users to call specific parts of the pipeline
# 					(e.g. only vcf plotting)
# 		- Add checkpointing
# 5) Generalize mapping and calling (perhaps by allowing users to
# 		add command lines as  strings)

from __future__ import division
from __future__ import print_function
import argparse
import csv
import os
import subprocess
import sys
import time
import numpy as np
import pandas as pd
import pybedtools
import pysam
import assemble
import bam
import reftools
import variants
# Setting the matplotlib display variable requires importing
# 	in exactly the following order:
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import seaborn as sns


def main():
	""" Main program"""

	# Version - placeholder for now - need to incorporate it into __init__.py
	version = "0.1"
	citation = """
	XYalign: Inferring Sex Chromosome Ploidy in NGS Data

	Timothy H Webster, Tanya Phung, Madeline Couse, Bruno Grande, Eric Karlins,
	Phillip Richmond, Whitney Whitford, Melissa A. Wilson Sayres

	2016

	Version: {}
	""".format(version)

	# Grab arguments
	args = parse_args()

	# Set up logfile
	logfile_path = os.path.join(args.output_dir, "logfiles")
	if args.logfile is not None:
		logfile = os.path.join(
			logfile_path, args.logfile)
	else:
		logfile = os.path.join(
			logfile_path, "{}_xyalign.log".format(
				args.sample_id))
	log_open = open(logfile, "w")

	# Print XYalign info and set up dictionary of version and parameters for
	# bam header updating
	print("{}\n\n".format(citation))
	log_open.write("{}\n\n".format(citation))
	print("{}\n".format("Parameters:"))
	log_open.write("{}\n\n".format("Parameters:"))

	xyalign_params_dict = {'ID': 'XYalign', 'VN': version, 'CL': []}
	for arg in args.__dict__:
		print("{}:\t{}".format(arg, args.__dict__[arg]))
		log_open.write("{}:\t{}\n".format(arg, args.__dict__[arg]))
		xyalign_params_dict['CL'].append("{}={}".format(arg, args.__dict__[arg]))

	print("\n")
	log_open.write("\n\n")

	print("Beginning Pipeline at {}\n".format(
		time.asctime(time.localtime(time.time()))))
	log_open.write("Beginning Pipeline at {}\n\n".format(
		time.asctime(time.localtime(time.time()))))

	# Initialize timer
	start_time = time.time()

	# Setup output paths
	fastq_path = os.path.join(args.output_dir, "fastq")
	bam_path = os.path.join(args.output_dir, "bam")
	reference_path = os.path.join(args.output_dir, "reference")
	bed_path = os.path.join(args.output_dir, "bed")
	vcf_path = os.path.join(args.output_dir, "vcf")
	plots_path = os.path.join(args.output_dir, "plots")
	results_path = os.path.join(args.output_dir, "results")

	# Create paths for output files
	noprocessing_vcf = os.path.join(
		vcf_path, "{}.noprocessing.vcf".format(
			args.sample_id))
	postprocessing_vcf = os.path.join(
		vcf_path, "{}.postprocessing.vcf".format(
			args.sample_id))
	if args.platypus_logfile is not None:
		plat_log = args.platypus_logfile
	else:
		plat_log = args.sample_id
	noprocessing_vcf_log = os.path.join(
		logfile_path, "{}_noprocessing_platypus.log".format(
			plat_log))
	postprocessing_vcf_log = os.path.join(
		logfile_path, "{}_postprocessing_platypus.log".format(
			plat_log))
	readbalance_prefix_noprocessing = os.path.join(
		plots_path, "{}_noprocessing".format(args.sample_id))
	readbalance_prefix_postprocessing = os.path.join(
		plots_path, "{}_postprocessing".format(args.sample_id))
	depth_mapq_prefix_noprocessing = os.path.join(
		plots_path, "{}_noprocessing".format(args.sample_id))
	depth_mapq_prefix_postprocessing = os.path.join(
		plots_path, "{}_postprocessing".format(args.sample_id))
	if args.high_quality_bed_out is not None:
		# high_prefix = args.high_quality_bed_out
		print(
			"--high_quality_bed_out is currently unsupported.  Please remove "
			"this flag")
		sys.exit(1)
	else:
		high_prefix = "{}_highquality_preprocessing".format(args.sample_id)
	output_bed_high = os.path.join(
		bed_path, "{}.bed".format(high_prefix))
	if args.low_quality_bed_out is not None:
		# low_prefix = args.low_quality_bed_out
		print(
			"--low_quality_bed_out is currently unsupported.  Please remove "
			"this flag")
	else:
		low_prefix = "{}_lowquality_preprocessing".format(args.sample_id)
	output_bed_low = os.path.join(
		bed_path, "{}.bed".format(low_prefix))
	if args.high_quality_bed_out is not None:
		# high_prefix_postprocessing = args.high_quality_bed_out
		print(
			"--high_quality_bed_out is currently unsupported.  Please remove "
			"this flag")
	else:
		high_prefix_postprocessing = "{}_highquality_postprocessing".format(
			args.sample_id)
	output_bed_high_postprocessing = os.path.join(
		bed_path, "{}.bed".format(high_prefix))
	if args.low_quality_bed_out is not None:
		# low_prefix_postprocessing = args.low_quality_bed_out
		print(
			"--low_quality_bed_out is currently unsupported.  Please remove "
			"this flag")
	else:
		low_prefix_postprocessing = "{}_lowquality_postprocessing".format(
			args.sample_id)
	output_bed_low_postprocessing = os.path.join(
		bed_path, "{}.bed".format(low_prefix))

	# First round of Platypus calling and plotting
	if args.platypus_calling == "both" or args.platypus_calling == "before":
		print("Beginning Platypus variant calling on unprocessed bam, {}\n".format(
			args.bam))
		platy_start = time.time()
		if args.bam is not None:
			a = variants.platypus_caller(
				args.platypus_path, noprocessing_vcf_log, args.bam, args.ref,
				args.chromosomes, args.cpus, noprocessing_vcf, None)
			platy_end = time.time()
			print(
				"\nPlatypus calling complete on {}. Elapsed Time: {} seconds\n\n".format(
					args.bam, (platy_end - platy_start)))
			log_open.write("Platypus calling on {}. Elapsed time: {} seconds\n".format(
				args.bam, (platy_end - platy_start)))
			if a != 0:
				print("Error in initial Platypus calling.")
				sys.exit(1)
			if args.no_variant_plots is not True:
				plot_var_begin = time.time()
				print("Beginning plotting of vcf, {}\n".format(noprocessing_vcf))
				variants.plot_variants_per_chrom(
					args.chromosomes, noprocessing_vcf,
					args.sample_id, readbalance_prefix_noprocessing,
					args.variant_quality_cutoff, args.marker_size,
					args.marker_transparency, args.bam)
				plot_var_end = time.time()
				print("\nVCF plotting complete on {}. Elapsed Time: {} seconds\n\n".format(
					noprocessing_vcf, (plot_var_end - plot_var_begin)))
				log_open.write("VCF plotting on {}. Elapsed time: {} seconds\n".format(
					noprocessing_vcf, (plot_var_end - plot_var_begin)))
		else:
			a = variants.platypus_caller(
				args.platypus_path, noprocessing_vcf_log, args.cram, args.ref,
				args.chromosomes, args.cpus, noprocessing_vcf, None)
			platy_end = time.time()
			print(
				"Platypus calling complete on {}. Elapsed Time: {} seconds\n\n".format(
					args.bam, (platy_end - platy_timer)))
			log_open.write("Platypus calling on {}. Elapsed time: {} seconds\n".format(
				args.bam, (platy_end - platy_timer)))
			if a != 0:
				print("Error in initial Platypus calling.")
				sys.exit(1)
			if args.no_variant_plots is not True:
				plot_var_begin = time.time()
				print("Beginning plotting of vcf, {}\n".format(noprocessing_vcf))
				variants.plot_variants_per_chrom(
					args.chromosomes, noprocessing_vcf,
					args.sample_id, readbalance_prefix_noprocessing,
					args.variant_quality_cutoff, args.marker_size,
					args.marker_transparency, args.cram)
				print("VCF plotting complete on {}. Elapsed Time: {} seconds\n\n".format(
					noprocessing_vcf, (plot_var_end - plot_var_begin)))
				log_open.write("VCF plotting on {}. Elapsed time: {} seconds\n".format(
					noprocessing_vcf, (plot_var_end - plot_var_begin)))

	# Analyze bam for depth and mapq
	if args.no_bam_analysis is not True:
		bam_analysis_start = time.time()
		if args.bam is not None:
			print("Beginning bam analyses on {}\n".format(args.bam))
			samfile = pysam.AlignmentFile(args.bam, "rb")
		else:
			print("Beginning cram analyses on {}\n".format(args.cram))
			samfile = pysam.AlignmentFile(args.cram, "rc")
		pass_df = []
		fail_df = []
		for chromosome in args.chromosomes:
			data = bam.traverse_bam_fetch(samfile, chromosome, args.window_size)
			tup = make_region_lists(
				data["windows"], args.mapq_cutoff, args.depth_filter)
			pass_df.append(tup[0])
			fail_df.append(tup[1])
			plot_depth_mapq(
				data, depth_mapq_prefix_noprocessing, args.sample_id,
				bam.get_length(samfile, chromosome), args.marker_size,
				args.marker_transparency)
		output_bed(output_bed_high, *pass_df)
		output_bed(output_bed_low, *fail_df)
		bam_analysis_end = time.time()
		print("Bam-cram analyses complete. Elapsed time: {} seconds\n".format(
			bam_analysis_end - bam_analysis_start))
		if args.bam is not None:
			log_open.write(
				"Bam analyses complete on {}. Elapsed time: {} seconds\n".format(
					args.bam, (bam_analysis_end - bam_analysis_start)))
		else:
			log_open.write(
				"Cram analyses complete on {}. Elapsed time: {} seconds\n".format(
					args.cram, (bam_analysis_end - bam_analysis_start)))

	# Infer ploidy (needs to be finished)

	# Replace this with code to infer ploidy, etc.
	# Permutation tests
	if args.no_perm_test is not True:
		perm_start = time.time()
		print("Beginning permutation tests\n")
		if args.y_chromosome is not None:
			sex_chromosomes = args.x_chromosome + args.y_chromosome
			autosomes = [x for x in args.chromosomes if x not in sex_chromosomes]
			perm_res_x = []
			perm_res_y = []
			for c in autosomes:
				perm_res_x.append(ploidy.permutation_test_chromosomes(
					pd.concat(pass_df), c, str(args.x_chromosome[0]), "chrom",
					"depth", args.num_permutations,
					results_path + "/{}_{}_permutation_results.txt".format(
						c, str(args.x_chromosome[0]))))
				perm_res_y.append(ploidy.permutation_test_chromosomes(
					pd.concat(pass_df), c, str(args.y_chromosome[0]), "chrom",
					"depth", args.num_permutations,
					results_path + "/{}_{}_permutation_results.txt".format(
						c, str(args.y_chromosome[0]))))
			sex_perm_res = ploidy.permutation_test_chromosomes(
				pd.concat(pass_df), str(args.x_chromosome[0]), str(args.y_chromosome[0]),
				"chrom", "depth", args.num_permutations,
				results_path + "/{}_{}_permutation_results.txt".format(
					str(args.x_chromosome[0]), str(args.y_chromosome[0])))

			# Right now this implements a simple and rather inelegant test for
			# 	a Y chromosome that assumes approximately equal depth on the
			# 	X and the Y in XY individuals.
			if sex_perm_res[3] < 1.0 < sex_perm_res[4]:
				y_present_perm = True
			else:
				y_present_perm = False
		else:
			sex_chromosomes = args.x_chromosome
			autosomes = [x for x in args.chromosomes if x not in sex_chromosomes]
			perm_res_x = []
			for c in autosomes:
				perm_res_x.append(ploidy.permutation_test_chromosomes(
					pd.concat(pass_df), c, str(args.x_chromosome[0]), "chrom",
					"depth", args.num_permutations,
					results_path + "/{}_{}_permutation_results.txt".format(
						c, str(args.x_chromosome[0]))))

			# Right now this implements a simple and rather inelegant test for
			# 	a Y chromosome that assumes approximately equal depth on the
			# 	X and the Y in XY individuals.
			# if 0.025 < sex_perm_res[2] < 0.95:
			# 	y_present_perm = True
			# else:
			# 	y_present_perm = False

		perm_end = time.time()
		print("Permutation tests complete.  Elapsed time: {} seconds\n\n".format(
			perm_end - perm_start))
		log_open.write(
			"Permutation tests complete.  Elapsed time: {} seconds\n".format(
				perm_end - perm_start))

	if args.y_present is True:
		y_present = True
		print("User set Y chromosome as present\n\n")
		log_open.write("User set Y chromosome as present\n")
	elif args.y_absent is True:
		y_present = False
		print("User set Y chromosome as absent\n\n")
		log_open.write("User set Y chromosome as absent\n")
	else:
		y_present = y_present_perm
		if y_present is True:
			print("Y chromosome inferred to be present\n\n")
			log_open.write("Y chromosome inferred to be present\n")
		else:
			print("Y chromosome inferred to be absent\n\n")
			log_open.write("Y chromosome inferred to be absent\n")

	# Likelihood analyses

	# Remapping
	if args.no_remapping is not True:
		print("Beginning remapping steps\n")
		if y_present is True:
			if args.reference_mask != [None]:
				if len(args.reference_mask) > 1:
					reference_mask = merge_bed_files("{}/reference_mask.merged.bed".format(
						bed_path), *args.reference_mask)
				else:
					reference_mask = args.reference_mask[0]
				# Isolate sex chromosomes from reference and index new reference
				new_ref_start = time.time()
				print("Creating new reference\n")
				new_reference = reftools.create_masked_reference(
					args.samtools_path, args.ref, "{}/{}.sex_chroms".format(
						reference_path, args.sample_id), reference_mask)
				new_ref_end = time.time()
				print("New reference complete. Elapsed time: {} seconds\n\n".format(
					new_ref_end - new_ref_start))
				log_open.write("New reference complete. Elapsed time: {} seconds\n".format(
					new_ref_end - new_ref_start))
				# Strip reads from sex chromosomes
				strip_reads_start = time.time()
				print("Stripping and cleaning reads from sex chromosomes\n")
				if args.bam is not None:
					new_fastqs = bam.bam_to_fastq(
						args.samtools_path, args.repairsh_path, args.bam,
						args.single_end, fastq_path, args.sample_id,
						args.x_chromosome + args.y_chromosome)
				else:
					new_fastqs = bam.bam_to_fastq(
						args.samtools_path, args.repairsh_path, args.cram,
						args.single_end, fastq_path, args.sample_id,
						args.x_chromosome + args.y_chromosome)
				strip_reads_end = time.time()
				print("Stripping reads complete. Elapsed time: {} seconds\n\n".format(
					strip_reads_end - strip_reads_start))
				log_open.write(
					"Stripping reads complete. Elapsed time: {} seconds\n".format(
						strip_reads_end - strip_reads_start))
				# Remap
				remap_start = time.time()
				print("Beginning remapping reads to new reference\n")
				with open(new_fastqs[0]) as f:
					read_group_and_fastqs = [line.strip() for line in f]
					read_group_and_fastqs = [x.split() for x in read_group_and_fastqs]
				with open(new_fastqs[1]) as f:
					read_group_headers = [line.split() for line in f]
				temp_bam_list = []
				for i in read_group_and_fastqs:
					if i != [""]:
						rg_id = i[0]
						fastq_files = i[1:]
						for j in read_group_headers:
							for k in j:
								if k[0:2] == 'ID':
									if k[3:] == rg_id:
										rg_tag = "\t".join(j)
									break
						temp_bam = assemble.bwa_mem_mapping_sambamba(
							args.bwa_path, args.samtools_path, args.sambamba_path,
							new_reference, "{}/{}.sex_chroms.{}.".format(
								bam_path, args.sample_id, rg_id),
							fastq_files, args.cpus, rg_tag,
							[str(x).strip() for x in args.bwa_flags.split()])
						temp_bam_list.append(temp_bam)
				remap_end = time.time()
				print("Remapping complete. Elapsed time: {} seconds\n\n".format(
					remap_end - remap_start))
				log_open.write("Remapping complete. Elapsed time: {} seconds\n".format(
					remap_end - remap_start))

				if len(temp_bam_list) < 2:
					new_bam = temp_bam_list[0]
				else:
					merge_start = time.time()
					print("Merging bams from different read groups\n")
					new_bam = bam.sambamba_merge(
						args.sambamba_path, temp_bam_list, "{}/{}.sex_chroms".format(
							bam_path, args.sample_id), args.cpus)
					merge_end = time.time()
					print(
						"Merging bams from different reads groups complete. "
						"Elapsed time: {} seconds\n\n".format(
							merge_end - merge_start))
					log_open.write(
						"Merging bams from different reads groups complete. "
						"Elapsed time: {} seconds\n".format(
							merge_end - merge_start))
				# Merge bam files
				switch_bam_start = time.time()
				print("Replacing old sex chromosomes with new in bam\n")
				if args.bam is not None:
					merged_bam = bam.switch_sex_chromosomes_bam_sambamba_output_temps(
						args.samtools_path, args.sambamba_path, args.bam, new_bam,
						args.x_chromosome + args.y_chromosome,
						bam_path, args.sample_id, args.cpus, xyalign_params_dict)
				else:
					merged_bam = bam.switch_sex_chromosomes_bam_sambamba_output_temps(
						args.samtools_path, args.sambamba_path, args.cram, new_bam,
						args.x_chromosome + args.y_chromosome,
						bam_path, args.sample_id, args.cpus, xyalign_params_dict)
				switch_bam_end = time.time()
				print(
					"Sex chromosome replacement (bam) complete: "
					"Elapsed time: {} seconds\n\n".format(switch_bam_end - switch_bam_start))
				log_open.write(
					"Sex chromosome replacement (bam) complete: "
					"Elapsed time: {} seconds\n".format(switch_bam_end - switch_bam_start))
			else:
				print(
					"Y chromosome present, but no mask provided (--reference_mask). "
					"Skipping remapping\n")
				log_open.write(
					"Y chromosome present, but no mask provided (--reference_mask). "
					"Skipping remapping\n")
		else:
			# Create Y mask and combine it with other masks
				# Note - doesn't handle CRAM yet
			y_mask = chromosome_bed(args.bam, "{}/{}.mask.bed".format(
				bed_path, args.y_chromosome))
			if args.reference_mask != [None]:
				reference_mask = merge_bed_files("{}/reference_mask.merged.bed".format(
					bed_path), y_mask, *args.reference_mask)
			else:
				reference_mask = y_mask
			# Isolate sex chromosomes from reference and index new reference
				new_ref_start = time.time()
				print("Creating new reference\n")
				new_reference = reftools.create_masked_reference(
					args.samtools_path, args.ref, "{}/{}.sex_chroms".format(
						reference_path, args.sample_id), reference_mask)
				new_ref_end = time.time()
				print("New reference complete. Elapsed time: {} seconds\n\n".format(
					new_ref_end - new_ref_start))
				log_open.write("New reference complete. Elapsed time: {} seconds\n".format(
					new_ref_end - new_ref_start))
			# Strip reads from sex chromosomes
			strip_reads_start = time.time()
			print("Stripping and cleaning reads from sex chromosomes\n")
			if args.bam is not None:
				new_fastqs = bam.bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.bam,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome)
			else:
				new_fastqs = bam.bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.cram,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome)
			strip_reads_end = time.time()
			print("Stripping reads complete. Elapsed time: {} seconds\n\n".format(
				strip_reads_end - strip_reads_start))
			log_open.write(
				"Stripping reads complete. Elapsed time: {} seconds\n".format(
					strip_reads_end - strip_reads_start))
			# Remap
			remap_start = time.time()
			print("Beginning remapping reads to new reference\n")
			with open(new_fastqs[0]) as f:
				read_group_and_fastqs = [line.strip() for line in f]
				read_group_and_fastqs = [x.split() for x in read_group_and_fastqs]
			with open(new_fastqs[1]) as f:
				read_group_headers = [line.split() for line in f]
			temp_bam_list = []
			for i in read_group_and_fastqs:
				if i != [""]:
					rg_id = i[0]
					fastq_files = i[1:]
					for j in read_group_headers:
						for k in j:
							if k[0:2] == 'ID':
								if k[3:] == rg_id:
									rg_tag = "\t".join(j)
								break
					temp_bam = assemble.bwa_mem_mapping_sambamba(
						args.bwa_path, args.samtools_path, args.sambamba_path,
						new_reference, "{}/{}.sex_chroms.{}.".format(
							bam_path, args.sample_id, rg_id),
						fastq_files, args.cpus, rg_tag,
						[str(x).strip() for x in args.bwa_flags.split()])
					temp_bam_list.append(temp_bam)
			remap_end = time.time()
			print("Remapping complete. Elapsed time: {} seconds\n\n".format(
				remap_end - remap_start))
			log_open.write("Remapping complete. Elapsed time: {} seconds\n".format(
				remap_end - remap_start))

			if len(temp_bam_list) < 2:
				new_bam = temp_bam_list[0]
			else:
				merge_start = time.time()
				print("Merging bams from different read groups\n")
				new_bam = bam.sambamba_merge(
					args.sambamba_path, temp_bam_list, "{}/{}.sex_chroms".format(
						bam_path, args.sample_id), args.cpus)
				merge_end = time.time()
				print(
					"Merging bams from different reads groups complete. "
					"Elapsed time: {} seconds\n\n".format(
						merge_end - merge_start))
				log_open.write(
					"Merging bams from different reads groups complete. "
					"Elapsed time: {} seconds\n".format(
						merge_end - merge_start))
			# Merge bam files
			print("Replacing old sex chromosomes with new in bam\n")
			if args.bam is not None:
				merged_bam = bam.switch_sex_chromosomes_bam_sambamba_output_temps(
					args.samtools_path, args.sambamba_path, args.bam, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus, xyalign_params_dict)
			else:
				merged_bam = bam.switch_sex_chromosomes_bam_sambamba_output_temps(
					args.samtools_path, args.sambamba_path, args.cram, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus, xyalign_params_dict)
				switch_bam_end = time.time()
			print(
				"Sex chromosome replacement (bam) complete: "
				"Elapsed time: {} seconds\n\n".format(switch_bam_end - switch_bam_start))
			log_open.write(
				"Sex chromosome replacement (bam) complete: "
				"Elapsed time: {} seconds\n".format(switch_bam_end - switch_bam_start))

	# Analyze new bam for depth and mapq
	if args.no_bam_analysis is not True and args.no_remapping is not True:
		bam_analysis_start = time.time()
		if args.bam is not None:
			print("Beginning final bam analyses on {}\n".format(merged_bam))
			samfile = pysam.AlignmentFile(merged_bam, "rb")
		else:
			print("Beginning final cram analyses on {}\n".format(merged_bam))
			samfile = pysam.AlignmentFile(merged_bam, "rc")
		pass_df_second = []
		fail_df_second = []
		for chromosome in args.chromosomes:
			data = bam.traverse_bam_fetch(samfile, chromosome, args.window_size)
			tup = make_region_lists(
				data["windows"], args.mapq_cutoff, args.depth_filter)
			pass_df_second.append(tup[0])
			fail_df_second.append(tup[1])
			plot_depth_mapq(
				data, depth_mapq_prefix_postprocessing, args.sample_id,
				bam.get_length(samfile, chromosome), args.marker_size,
				args.marker_transparency)
		output_bed(output_bed_high_postprocessing, *pass_df_second)
		output_bed(output_bed_low_postprocessing, *fail_df_second)
		bam_analysis_end = time.time()
		print("Final bam-cram analyses complete. Elapsed time: {} seconds\n".format(
			bam_analysis_end - bam_analysis_start))
		if args.bam is not None:
			log_open.write(
				"Final bam analyses complete on {}. Elapsed time: {} seconds\n".format(
					merged_bam, (bam_analysis_end - bam_analysis_start)))
		else:
			log_open.write(
				"Final cram analyses complete on {}. Elapsed time: {} seconds\n".format(
					merged_bam, (bam_analysis_end - bam_analysis_start)))

	# Final round of calling and plotting
	include_bed = output_bed_high_postprocessing

	if args.platypus_calling == "both" or args.platypus_calling == "after":
		a = variants.platypus_caller(
			args.platypus_path, postprocessing_vcf_log, merged_bam, args.ref,
			args.chromosomes, args.cpus, postprocessing_vcf, include_bed)
		if a != 0:
			print("Error in second round of Platypus calling.")
			sys.exit(1)
		if args.no_variant_plots is not True:
			variants.plot_variants_per_chrom(
				args.chromosomes,
				postprocessing_vcf,
				args.sample_id, readbalance_prefix_postprocessing,
				args.variant_quality_cutoff, args.marker_size,
				args.marker_transparency, merged_bam)

	# Final timestamp
	end_time = time.time()
	print(
		"XYalign complete. Elapsed time: {} seconds\n".format(end_time - start_time))
	log_open.write("XYalign complete. Elapsed time: {} seconds\n".format(
		end_time - start_time))

	# Close log file
	log_open.close()


def parse_args():
	"""Parse command-line arguments"""
	parser = argparse.ArgumentParser(description="XYalign")

	parser.add_argument(
		"--ref", required=True,
		help="REQUIRED. Path to reference sequence (including file name).")

	parser.add_argument(
		"--output_dir", "-o",
		help="REQUIRED. Output directory. XYalign will create a directory "
		"structure within this directory")

	parser.add_argument(
		"--chromosomes", "-c", nargs="+", default=["chrX", "chrY", "chr19"],
		help="Chromosomes to analyze (names must match reference exactly). "
		"Defaults to chr19, chrX, chrY.")

	parser.add_argument(
		"--x_chromosome", "-x", nargs="+", default=["chrX"],
		help="Names of x-linked scaffolds in reference fasta (must match "
		"reference exactly).  Defaults to chrX.")

	parser.add_argument(
		"--y_chromosome", "-y", nargs="+", default=["chrY"],
		help="Names of y-linked scaffolds in reference fasta (must match "
		"reference exactly). Defaults to chrY. Give None if using an assembly "
		"without a Y chromosome")

	parser.add_argument(
		"--sample_id", "-id", default="sample",
		help="Name/ID of sample - for use in plot titles and file naming. "
		"Default is sample")

	parser.add_argument(
		"--cpus", type=int, default=1,
		help="Number of cores/threads to use. Default is 1")

	parser.add_argument(
		"--logfile", default=None,
		help="Name of logfile.  Will overwrite if exists.  Default is "
		"sample_xyalign.log")

	parser.add_argument(
		"--single_end", action="store_true", default=False,
		help="Include flag if reads are single-end and NOT paired-end.")

	# Program paths
	parser.add_argument(
		"--platypus_path", default="platypus",
		help="Path to platypus.  Default is 'platypus'")

	parser.add_argument(
		"--bwa_path", default="bwa",
		help="Path to bwa. Default is 'bwa'")

	parser.add_argument(
		"--samtools_path", default="samtools",
		help="Path to samtools. Default is 'samtools'")

	parser.add_argument(
		"--repairsh_path", default="repair.sh",
		help="Path to bbmap's repair.sh script. Default is 'repair.sh'")

	parser.add_argument(
		"--sambamba_path", default="sambamba",
		help="Path to sambamba. Default is 'sambamba'")

	# Options for turning on/off parts of the pipeline
	parser.add_argument(
		"--no_remapping", action="store_true", default=False,
		help="Include this flag to prevent remapping sex chromosome reads.")

	parser.add_argument(
		"--platypus_calling", default="both",
		choices=["both", "none", "before", "after"],
		help="Platypus calling withing the pipeline "
		"(before processing, after processing, both, "
		"or neither). Options: both, none, before, after.")

	parser.add_argument(
		"--no_variant_plots", action="store_true", default=False,
		help="Include flag to prevent plotting read balance from VCF files.")

	parser.add_argument(
		"--no_bam_analysis", action="store_true", default=False,
		help="Include flag to prevent depth/mapq analysis of bam file")

	# Variant Calling Flags
	parser.add_argument(
		"--variant_quality_cutoff", "-vqc", type=int, default=20,
		help="Consider all SNPs with a quality greater than or "
		"equal to this value. Default is 20.")

	parser.add_argument(
		"--platypus_logfile", default=None,
		help="Prefix to use for Platypus log files.  Will default to the "
		"sample_id argument provided")

	# Mapping/remapping Flags
	parser.add_argument(
		"--reference_mask", nargs="+", default=[None],
		help="Bed file containing regions to replace with Ns in the sex "
		"chromosome reference.  Examples might include the pseudoautosomal "
		"regions on the Y to force all mapping/calling on those regions of the "
		"X chromosome.  Default is none.")

	parser.add_argument(
		"--xx_reference", default=None,
		help="Path to preprocessed reference fasta to be used for remapping in "
		"X0 or XX samples.  Default is None.  If none, will produce a "
		"sample-specific reference for remapping.")

	parser.add_argument(
		"--xy_reference", default=None,
		help="Path to preprocessed reference fasta to be used for remapping in "
		"samples containing Y chromosome.  Default is None.  If none, will "
		"produce a sample-specific reference for remapping.")

	parser.add_argument(
		"--bwa_flags", type=str, default="",
		help="Provide a string (in quotes, with spaces between arguments) "
		"for additional flags desired for BWA mapping (other than -R and -t). "
		"Example: '-M -T 20 -v 4'.  Note that those are spaces between "
		"arguments.")

	# Bam Analysis Flags
	parser.add_argument(
		"--window_size", "-w", type=int, default=50000,
		help="Window size (integer) for sliding window calculations. Default "
		"is 50000.")

	parser.add_argument(
		"--mapq_cutoff", "-mq", type=int, default=20,
		help="Minimum mean mapq threshold for a window to be "
		"considered high quality. Default is 20.")

	parser.add_argument(
		"--depth_filter", "-df", type=float, default=4.0,
		help="Filter for depth (f), where the threshold used is mean_depth +- "
		"(f * square_root(mean_depth)).  See Li 2014 (Bioinformatics 30: "
		"2843-2851) for more information.  Default is 4.")

	parser.add_argument(
		"--high_quality_bed_out", "-hq", default=None,
		help="Prefix of output file for high quality regions. Defaults to "
		"sample_id_highquality")

	parser.add_argument(
		"--low_quality_bed_out", "-lq", default=None,
		help="Prefix of output file for low quality regions. Defaults to "
		"sample_id_lowquality")

	parser.add_argument(
		"--num_permutations", type=int, default=10000,
		help="Number of permutations to use for permutation analyses. "
		"Default is 10000")

	# Plotting flags
	parser.add_argument(
		"--marker_size", type=float, default=10.0,
		help="Marker size for genome-wide plots in matplotlib. Default is 10.")

	parser.add_argument(
		"--marker_transparency", "-mt", type=float, default=0.5,
		help="Transparency of markers in genome-wide plots.  "
		"Alpha in matplotlib.  Default is 0.5")

	# Mutually exclusive group 1 - bam or cram file
	group = parser.add_mutually_exclusive_group(required=True)

	group.add_argument(
		"--bam", help="Input bam file.")

	group.add_argument(
		"--cram", help="Input cram file.")

	# Mutally exclusive group 2 - overriding ploidy estimation with declaration
	# 		that Y is present or Y is absent.  --no_perm_test explicitly
	# 		requires one of either --y_present or --y_absent, but the reverse
	# 		is not true (i.e., if you don't run tests, you need to tell
	# 		XY align what the ploidy is, however you can tell XY align what
	# 		the ploidy is and still run the permutation analyses, the results
	# 		of which will be ignored)

	parser.add_argument(
		"--no_perm_test", action="store_true", default=False,
		help="Include flag to turn off permutation tests. Requires either "
		"--y_present or --y_absent to also be called")

	group2 = parser.add_mutually_exclusive_group(required=False)

	group2.add_argument(
		"--y_present", action="store_true", default=False,
		help="Overrides sex chr estimation by XYalign and remaps with Y present.")

	group2.add_argument(
		"--y_absent", action="store_true", default=False,
		help="Overrides sex chr estimation by XY align and remaps with Y absent.")

	args = parser.parse_args()

	# Validate permutation test arguments
	if args.no_perm_test is True:
		if args.y_present is False and args.y_absent is False:
			print("Error. Either --y_present or --y_absent needs to be "
									"included with --no_perm_test")
		sys.exit(1)
	if args.platypus_calling not in ["both", "none", "before", "after"]:
		print("Error. Platypus calling must be both, none, before, or after. "
								"Default is both.")
		sys.exit(1)

	# Validate chromosome arguments
	if len(args.chromosomes) == 0:
		print("Please provide chromosome names to analyze (--chromosomes)")
		sys.exit(1)
	elif len(args.chromosomes) == 1:
		if args.no_perm_test is False:
			print(
				"You only provided a single chromosome to analyze. At minimum "
				"include the flag --no_perm_test, but think carefully about "
				"how this will affect analyses.  We recommend including at "
				"least one autosome, X, and Y when possible.")
			sys.exit(1)
		else:
			print(
				"You only provided a single chromosome to analyze. You "
				"included the flag --no_perm_test, so XYalign will continue, "
				"but think carefully about "
				"how this will affect analyses.  We recommend including at "
				"least one autosome, X, and Y when possible.")

	# Validate bwa arguments
	bwa_args = [str(x).strip() for x in args.bwa_flags.split()]
	red_list = ["-rm", "rm", "-rf", "rf", "-RM", "RM", "-RF", "RF"]
	if any(x in bwa_args for x in red_list):
		print(
			"Found either rm or rf in your bwa flags. Exiting to prevent "
			"unintended shell consequences")
		sys.exit(1)
	yellow_list = ["-R", "-t"]
	if any(x in bwa_args for x in yellow_list):
		print(
			"Found either -R or -t in bwa flags.  These flags are already used "
			"in XYalign.  Please remove.")
		sys.exit(1)

	# Create directory structure if not already in place
	if not os.path.exists(os.path.join(args.output_dir, "fastq")):
		os.makedirs(os.path.join(args.output_dir, "fastq"))
	if not os.path.exists(os.path.join(args.output_dir, "bam")):
		os.makedirs(os.path.join(args.output_dir, "bam"))
	if not os.path.exists(os.path.join(args.output_dir, "reference")):
		os.makedirs(os.path.join(args.output_dir, "reference"))
	if not os.path.exists(os.path.join(args.output_dir, "bed")):
		os.makedirs(os.path.join(args.output_dir, "bed"))
	if not os.path.exists(os.path.join(args.output_dir, "vcf")):
		os.makedirs(os.path.join(args.output_dir, "vcf"))
	if not os.path.exists(os.path.join(args.output_dir, "plots")):
		os.makedirs(os.path.join(args.output_dir, "plots"))
	if not os.path.exists(os.path.join(args.output_dir, "results")):
		os.makedirs(os.path.join(args.output_dir, "results"))
	if not os.path.exists(os.path.join(args.output_dir, "logfiles")):
		os.makedirs(os.path.join(args.output_dir, "logfiles"))

	# Return arguments namespace
	return args


def chromosome_bed(bamfile, output_file, chromosome_list):
	"""
	Takes list of chromosomes and outputs a bed file with the length of each
	chromosome on each line (e.g., chr1    0   247249719).

	args:
		bamfile: full path to bam file - for calculating length
		output_file: name of (including full path to) desired output file
		chromosome_list: list of chromosome/scaffolds to include

	returns:
		output_file
	"""
	with open(output_file, "w") as f:
		sam_file = pysam.AlignmentFile(bamfile, "rb")
		for i in chromosome_list:
			try:
				l = get_length(sam_file, i)
				f.write("{}\t{}\t{}\n".format(i, "0", l))
			except:
				print("Error finding chromosome length in bam file (for bed file)")
				sys.exit(1)
	return output_file


def merge_bed_files(ouput_file, *bed_files):
	"""
	This function simply takes an output_file (full path to desired ouput file)
	and an arbitrary number of external bed files (including full path),
	and merges the bed files into the output_file

	args:
		output_file: full path to and name of desired output bed file
		*bed_files: arbitrary number of external bed files (include full path)
	returns:
		path to output_file
	"""
	a = pybedtools.BedTool(bed_files[0])
	for i in bed_files[1:]:
		b = a.cat(i)
	c = b.sort().merge()
	c.saveas(output_file)
	return output_file


def make_region_lists(depthAndMapqDf, mapqCutoff, depth_thresh):
	"""
	Filters a pandas dataframe for mapq and depth

	depthAndMapqDf is a dataframe with 'depth' and 'mapq' columns
	mapqCutoff is the minimum mapq for a window to be considered high quality
	depth_thresh is the factor to use in filtering regions based on depth:
		Li (2014) recommends:
			mean_depth +- (depth_thresh * (depth_mean ** 0.5)),
				where depth_thresh is 3 or 4.

	Returns:
		A tuple containing two dataframes (passing, failing)
	"""
	depth_mean = depthAndMapqDf["depth"].mean()
	depth_sd = depthAndMapqDf["depth"].std()

	depthMin = depth_mean - (depth_thresh * (depth_mean ** 0.5))
	depthMax = depth_mean + (depth_thresh * (depth_mean ** 0.5))

	good = (
		(depthAndMapqDf.mapq >= mapqCutoff) &
		(depthAndMapqDf.depth > depthMin) &
		(depthAndMapqDf.depth < depthMax))
	dfGood = depthAndMapqDf[good]
	dfBad = depthAndMapqDf[~good]

	return (dfGood, dfBad)


def output_bed(outBed, *regionDfs):
	"""
	Takes a list of dataframes to concatenate and merge into an output bed file

	outBed is the full path to and name of the output bed file
	*regionDfs is an arbitrary number of dataframes to be included

	Returns:
		Nothing
	"""
	dfComb = pd.concat(regionDfs)
	regionList = dfComb.ix[:, "chrom":"stop"].values.tolist()
	merge = pybedtools.BedTool(regionList).sort().merge()
	with open(outBed, 'w') as output:
		output.write(str(merge))
	pass


def chromosome_wide_plot(
	chrom, positions, y_value, measure_name, sampleID, output_prefix,
	MarkerSize, MarkerAlpha, Xlim, Ylim):
	"""
	Plots values across a chromosome, where the x axis is the position along the
	chromosome and the Y axis is the value of the measure of interest.

	positions is an array of coordinates
	y_value is an array of the values of the measure of interest
	measure_name is the name of the measure of interest (y axis title)
	chromosome is the name of the chromosome being plotted
	sampleID is the name of the sample
	MarkerSize is the size in points^2
	MarkerAlpha is the transparency (0 to 1)
	Xlim is the maximum X value
	Ylim is the maximum Y value

	Returns:
		Nothing
	"""
	if "x" in chrom.lower():
		Color = "green"
	elif "y" in chrom.lower():
		Color = "blue"
	else:
		Color = "red"
	fig = plt.figure(figsize=(15, 5))
	axes = fig.add_subplot(111)
	axes.scatter(
		positions, y_value, c=Color, alpha=MarkerAlpha, s=MarkerSize, lw=0)
	axes.set_xlim(0, Xlim)
	axes.set_ylim(0, Ylim)
	axes.set_title("%s - %s" % (sampleID, chrom))
	axes.set_xlabel("Chromosomal Position")
	axes.set_ylabel(measure_name)
	plt.savefig("{}_{}_{}_GenomicScatter.svg".format(
		output_prefix, chrom, measure_name))
	plt.savefig("{}_{}_{}_GenomicScatter.png".format(
		output_prefix, chrom, measure_name))
	plt.close(fig)


def plot_depth_mapq(
	data_dict, output_prefix, sampleID, chrom_length, MarkerSize, MarkerAlpha):
	"""
	Takes a dictionary (output from traverseBam) and outputs histograms and
	genome-wide plots of various metrics.
	Args:
		data_dict: Dictionary of pandas data frames
		output_prefix: Path and prefix of output files to create
		sampleID: name/ID of sample
		chrom_length: length of chromosome
	Returns:
		Nothing
	"""

	window_df = None if "windows" not in data_dict else data_dict[
		"windows"]
	depth_hist = None if "depth_freq" not in data_dict else data_dict[
		"depth_freq"]
	readbal_hist = None if "readbal_freq" not in data_dict else data_dict[
		"readbal_freq"]
	mapq_hist = None if "mapq_freq" not in data_dict else data_dict[
		"mapq_freq"]

	chromosome = window_df["chrom"][1]

	# Create genome-wide plots based on window means
	if window_df is not None:
		# depth plot
		# depth_genome_plot_path = os.path.join(
		# 	output_dir, "depth_windows." + chromosome + ".png")
		# depth_genome_plot = sns.lmplot(
		# 	'start', 'depth', data=window_df, fit_reg=False,
		# 	scatter_kws={'alpha': 0.3})
		# depth_genome_plot.savefig(depth_genome_plot_path)
		chromosome_wide_plot(
			chromosome, window_df["start"].values, window_df["depth"].values,
			"Depth", sampleID, output_prefix,
			MarkerSize, MarkerAlpha,
			chrom_length, 100)

		# mapping quality plot
		# mapq_genome_plot_path = os.path.join(
		# 	output_dir, "mapq_windows." + chrom + ".png")
		# mapq_genome_plot = sns.lmplot(
		# 	'start', 'mapq', data=window_df, fit_reg=False)
		# mapq_genome_plot.savefig(mapq_genome_plot_path)
		chromosome_wide_plot(
			chromosome, window_df["start"].values, window_df["mapq"].values,
			"Mapq", sampleID, output_prefix,
			MarkerSize, MarkerAlpha, chrom_length, 80)

	# Create histograms
	# TODO: update filenames dynamically like window_df above
	# TODO: update Count column name
	if depth_hist is not None:
		depth_bar_plot = sns.countplot(
			x='depth', y='Count', data=depth_hist)
		depth_bar_plot.savefig("depth_hist.png")
	if readbal_hist is not None:
		balance_bar_plot = sns.countplot(
			x='ReadBalance', y='Count', data=readbal_hist)
		balance_bar_plot.savefig("readbalance_hist.png")
	if mapq_hist is not None:
		mapq_bar_plot = sns.countplot(
			x='Mapq', y='Count', data=mapq_hist)
		mapq_bar_plot.savefig("mapq_hist.png")

if __name__ == "__main__":
	main()

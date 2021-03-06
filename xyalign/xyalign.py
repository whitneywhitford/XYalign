# XYalign main program

from __future__ import division
from __future__ import print_function
import argparse
import logging
import os
import subprocess
import sys
import time
import pandas as pd
import pysam
import assemble
import bam
import ploidy
import reftools
import utils
import variants


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
		"--single_end", action="store_true", default=False,
		help="Include flag if reads are single-end and NOT paired-end.")

	# Options to run specific parts of the pipeline
	pipeline_group = parser.add_mutually_exclusive_group(required=False)
	pipeline_group.add_argument(
		"--PREPARE_REFERENCE", action="store_true", default=False,
		help="This flag will limit XYalign to only preparing reference fastas "
		"for individuals with and without Y chromosomes.  These fastas can "
		"then be passed with each sample to save subsequent processing time.")

	pipeline_group.add_argument(
		"--ANALYZE_BAM", action="store_true", default=False,
		help="This flag will limit XYalign to only analyzing the bam file for "
		"(optionally) depth, mapq, and read balance and outputting plots.")

	pipeline_group.add_argument(
		"--CHARACTERIZE_SEX_CHROMS", action="store_true", default=False,
		help="This flag will limit XYalign to the steps required to "
		"characterize sex chromosome content (i.e., analyzing the bam "
		"for depth, mapq, and read balance and running statistical tests "
		"to help infer ploidy)")

	pipeline_group.add_argument(
		"--REMAPPING", action="store_true", default=False,
		help="This flag will limit XYalign to only the steps required to "
		"strip reads and remap to masked references. If masked references "
		"are not provided, they will be created.")

	# Logging options
	parser.add_argument(
		"--logfile", default=None,
		help="Name of logfile.  Will overwrite if exists.  Default is "
		"sample_xyalign.log")

	parser.add_argument(
		"--reporting_level", default='INFO',
		choices=["DEBUG", "INFO", "ERROR", "CRITICAL"],
		help="Set level of messages printed to console. Default is 'INFO'. "
		"Choose from (in decreasing amount of reporting) DEBUG, INFO, ERROR "
		"or CRITICAL")

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

	parser.add_argument(
		"--skip_compatibility_check", action="store_true", default=False,
		help="Include flag to prevent check of compatibility between input bam "
		"and reference fasta")

	# Variant Calling Flags
	parser.add_argument(
		"--variant_quality_cutoff", "-vqc", type=int, default=20,
		help="Consider all SNPs with a quality greater than or "
		"equal to this value. Default is 20.")

	parser.add_argument(
		"--platypus_logfile", default=None,
		help="Prefix to use for Platypus log files.  Will default to the "
		"sample_id argument provided")

	# Reference-related Flags
	parser.add_argument(
		"--reference_mask", nargs="+", default=[None],
		help="Bed file containing regions to replace with Ns in the sex "
		"chromosome reference.  Examples might include the pseudoautosomal "
		"regions on the Y to force all mapping/calling on those regions of the "
		"X chromosome.  Default is none.")

	parser.add_argument(
		"--xx_ref_out", default=None,
		help="Desired name for masked output fasta for "
		"samples WITHOUT a Y chromosome (e.g., XX, XXX, XO, etc.). "
		"Defaults to 'xyalign_noY.masked.fa'. Will be output "
		"in the XYalign reference directory.")

	parser.add_argument(
		"--xy_ref_out", default=None,
		help="Desired name for masked output fasta for "
		"samples WITH a Y chromosome (e.g., XY, XXY, etc.). "
		"Defaults to 'xyalign_withY.masked.fa'. Will be output "
		"in the XYalign reference directory.")

	parser.add_argument(
		"--xx_ref_in", default=None,
		help="Path to preprocessed reference fasta to be used for remapping in "
		"X0 or XX samples.  Default is None.  If none, will produce a "
		"sample-specific reference for remapping.")

	parser.add_argument(
		"--xy_ref_in", default=None,
		help="Path to preprocessed reference fasta to be used for remapping in "
		"samples containing Y chromosome.  Default is None.  If none, will "
		"produce a sample-specific reference for remapping.")

	# Mapping/remapping arguments
	parser.add_argument(
		"--bwa_flags", type=str, default="",
		help="Provide a string (in quotes, with spaces between arguments) "
		"for additional flags desired for BWA mapping (other than -R and -t). "
		"Example: '-M -T 20 -v 4'.  Note that those are spaces between "
		"arguments.")

	parser.add_argument(
		"--sex_chrom_bam_only", action="store_true", default=False,
		help="This flag skips merging the new sex chromosome bam file back "
		"into the original bam file (i.e., sex chrom swapping). This will "
		"output a bam file containing only the newly remapped sex chromosomes.")

	# Bam Analysis Flags
	parser.add_argument(
		"--window_size", "-w", default=None,
		help="Window size (integer) for sliding window calculations. Default "
		"is 50000.  Default is None. If set to None, will use targets "
		"provided using --target_bed.")

	parser.add_argument(
		"--target_bed", default=None,
		help="Bed file containing targets to use in sliding window analyses "
		"instead of a fixed window width. Either this or --window_size needs "
		"to be set.  Default is None, which will use window size provided "
		"with --window_size.  If not None, and --window_size is None, analyses "
		"will use targets in provided file.  Must be typical bed format, "
		"0-based indexing, with the first three columns containing "
		"the chromosome name, start coordinate, stop coordinate.")

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

	parser.add_argument(
		"--num_bootstraps", type=int, default=10000,
		help="Number of bootstrap replicates to use when bootstrapping mean "
		"depth ratios among chromosomes. Default is 10000")

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

	parser.add_argument(
		"--no_ks_test", action="store_true", default=False,
		help="Include flag to turn off KS Two Sample tests. Requires either "
		"--y_present or --y_absent to also be called")

	parser.add_argument(
		"--no_bootstrap", action="store_true", default=False,
		help="Include flag to turn off bootstrap analyses. Requires either "
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

	# Validate sliding window options
	if args.window_size is not None and args.window_size != "None":
		if args.window_size.isdigit() is False:
			print(
				"--window_size needs to be either None or a positive integer. "
				"Exiting.")
			sys.exit(1)
	else:
		if args.target_bed is None:
			print(
				"If --window_size is None, --target_bed needs to be used. Exiting.")
			sys.exit(1)
		elif os.path.exists(args.target_bed) is False:
			print(
				"Invalid file provided with --target_bed. Check path. Exiting.")
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


def ref_prep():
	"""
	Reference prep part of the pipeline

	Returns a tuple with the two masked references (one with the y masked, "
	"one with the y present")
	"""
	# Combine masks, if more than one present
	if args.reference_mask != [None]:
		if len(args.reference_mask) > 1:
			reference_mask = utils.merge_bed_files(
				"{}/reference_mask.merged.bed".format(
					reference_path), *args.reference_mask)
		else:
			reference_mask = args.reference_mask[0]
	else:
		reference_mask = None
	# Create masked noY reference
	y_mask = utils.chromosome_bed(input_bam, "{}/Y.bed".format(
		reference_path), args.y_chromosome)
	if reference_mask is not None:
		noy_out = ref.mask_reference(
			utils.merge_bed_files(
				"{}/reference_mask.maskY.merged.bed".format(
					reference_path), reference_mask, y_mask), xx_out)
	else:
		noy_out = ref.mask_reference(y_mask, xx_out)
	noy_ref = reftools.RefFasta(noy_out, args.samtools_path, args.bwa_path)
	noy_ref.index_bwa()
	noy_ref.seq_dict()
	# Create masked withY reference
	if reference_mask is not None:
		withy_out = ref.mask_reference(reference_mask, xy_out)
	else:
		logger.info(
			"No reference mask provided, copying full reference to {} as "
			"XY reference to prevent damage, modification, etc. to original "
			"reference.".format(xy_out))
		subprocess.call(["cp", ref.filepath, xy_out])
		withy_out = xy_out
	withy_ref = reftools.RefFasta(withy_out, args.samtools_path, args.bwa_path)
	withy_ref.index_bwa()
	withy_ref.seq_dict()
	return (noy_ref, withy_ref)


def bam_analysis_noprocessing():
	"""
	Runs bam analyis part of pipeline for unprocessed bam files

	Returns a tuple containing two lists, one containing pandas dataframes with
	passing windows, and one containting pandas dataframes with failing windows
	"""
	# Platypus
	if args.platypus_calling in ["both", "before"]:
		a = variants.platypus_caller(
			args.platypus_path, noprocessing_vcf_log, input_bam.filepath,
			ref.filepath, args.chromosomes, args.cpus, noprocessing_vcf,
			None)
		if a != 0:
			logger.error("Error in platypus calling on {}".format(
				input_bam.filepath))
			sys.exit(1)
		if args.no_variant_plots is not True:
			variants.plot_variants_per_chrom(
				args.chromosomes, noprocessing_vcf,
				args.sample_id, readbalance_prefix_noprocessing,
				args.variant_quality_cutoff, args.marker_size,
				args.marker_transparency, input_bam)
	# Depth/MAPQ
	if args.no_bam_analysis is not True:
		pass_df = []
		fail_df = []
		for chromosome in args.chromosomes:
			if args.window_size is not None and args.window_size != "None":
				data = input_bam.analyze_bam_fetch(
					chromosome, int(args.window_size))
			else:
				data = input_bam.analyze_bam_fetch(
					chromosome, None, args.target_bed)
			tup = utils.make_region_lists(
				data["windows"], args.mapq_cutoff, args.depth_filter)
			pass_df.append(tup[0])
			fail_df.append(tup[1])
			utils.plot_depth_mapq(
				data, depth_mapq_prefix_noprocessing, args.sample_id,
				input_bam.get_chrom_length(chromosome), args.marker_size,
				args.marker_transparency)
		utils.output_bed(output_bed_high, *pass_df)
		utils.output_bed(output_bed_low, *fail_df)
	return(pass_df, fail_df)


def ploidy_analysis(passing_df, failing_df):
	"""
	Runs the ploidy analysis part of the pipeline.  Takes passing_df and
	failing_df (the output of bam_analysis_noprocessing()) as input.

	Returns a dictionary with results for each test.
	"""
	# Permutations
	if args.no_perm_test is False:
		if args.y_chromosome is not None:
			sex_chromosomes = args.x_chromosome + args.y_chromosome
			perm_res_x = []
			perm_res_y = []
		else:
			sex_chromosomes = args.x_chromosome
			perm_res_x = []
			perm_res_y = None
		autosomes = [
			x for x in args.chromosomes if x not in sex_chromosomes]
		for c in autosomes:
			perm_res_x.append(ploidy.permutation_test_chromosomes(
				pd.concat(passing_df), c,
				str(args.x_chromosome[0]), "chrom",
				"depth", args.num_permutations,
				results_path + "/{}.{}_{}_permutation_results.txt".format(
					args.sample_id, c, str(args.x_chromosome[0]))))
			if perm_res_y is not None:
				perm_res_y.append(ploidy.permutation_test_chromosomes(
					pd.concat(passing_df), c,
					str(args.y_chromosome[0]), "chrom",
					"depth", args.num_permutations,
					results_path + "/{}.{}_{}_permutation_results.txt".format(
						args.sample_id, c, str(args.y_chromosome[0]))))
		if perm_res_y is not None:
			sex_perm_res = ploidy.permutation_test_chromosomes(
				pd.concat(passing_df), str(args.x_chromosome[0]),
				str(args.y_chromosome[0]),
				"chrom", "depth", args.num_permutations,
				results_path + "/{}.{}_{}_permutation_results.txt".format(
					args.sample_id, str(args.x_chromosome[0]), str(args.y_chromosome[0])))

	# K-S Two Sample
	if args.no_ks_test is False:
		if args.y_chromosome is not None:
			sex_chromosomes = args.x_chromosome + args.y_chromosome
			ks_res_x = []
			ks_res_y = []
		else:
			sex_chromosomes = args.x_chromosome
			ks_res_x = []
			ks_res_y = None
		autosomes = [
			x for x in args.chromosomes if x not in sex_chromosomes]
		for c in autosomes:
			ks_res_x.append(ploidy.ks_two_sample(
				pd.concat(passing_df), c,
				str(args.x_chromosome[0]), "chrom", "depth",
				results_path + "/{}.{}_{}_ks_results.txt".format(
					args.sample_id, c, str(args.x_chromosome[0]))))
			if ks_res_y is not None:
				ks_res_y.append(ploidy.ks_two_sample(
					pd.concat(passing_df), c,
					str(args.y_chromosome[0]), "chrom", "depth",
					results_path + "/{}.{}_{}_ks_results.txt".format(
						args.sample_id, c, str(args.y_chromosome[0]))))
		if ks_res_y is not None:
			sex_ks_res = ploidy.ks_two_sample(
				pd.concat(passing_df), str(args.x_chromosome[0]),
				str(args.y_chromosome[0]), "chrom", "depth",
				results_path + "/{}.{}_{}_ks_results.txt".format(
					args.sample_id, str(args.x_chromosome[0]), str(args.y_chromosome[0])))
	# Bootstrap
	if args.no_bootstrap is False:
		if args.y_chromosome is not None:
			sex_chromosomes = args.x_chromosome + args.y_chromosome
			boot_res_x = []
			boot_res_y = []
		else:
			sex_chromosomes = args.x_chromosome
			boot_res_x = []
			boot_res_y = None
		autosomes = [
			x for x in args.chromosomes if x not in sex_chromosomes]
		for c in autosomes:
			boot_res_x.append(ploidy.bootstrap(
				pd.concat(passing_df), c,
				str(args.x_chromosome[0]), "chrom",
				"depth", args.num_bootstraps,
				results_path + "/{}.{}_{}_bootstrap_results.txt".format(
					args.sample_id, c, str(args.x_chromosome[0]))))
			if boot_res_y is not None:
				boot_res_y.append(ploidy.bootstrap(
					pd.concat(passing_df), c,
					str(args.y_chromosome[0]), "chrom",
					"depth", args.num_bootstraps,
					results_path + "/{}.{}_{}_bootstrap_results.txt".format(
						args.sample_id, c, str(args.y_chromosome[0]))))
		if boot_res_y is not None:
			sex_boot_res = ploidy.bootstrap(
				pd.concat(passing_df), str(args.x_chromosome[0]),
				str(args.y_chromosome[0]),
				"chrom", "depth", args.num_bootstraps,
				results_path + "/{}.{}_{}_bootstrap_results.txt".format(
					args.sample_id, str(args.x_chromosome[0]), str(args.y_chromosome[0])))
	return {
		"perm": [perm_res_x, perm_res_y, sex_perm_res],
		"ks": [ks_res_x, ks_res_y, sex_ks_res],
		"boot": [boot_res_x, boot_res_y, sex_boot_res]}


def remapping():
	"""
	Runs remapping steps of the pipeline

	Returns bam containing remapped sex chroms
	"""
	if y_present is True:
		new_reference = masked_refs[1]
	else:
		new_reference = masked_refs[0]
	new_fastqs = input_bam.strip_reads(
		args.repairsh_path, args.single_end, fastq_path, args.sample_id,
		args.x_chromosome + args.y_chromosome)
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
				new_reference.filepath, "{}/{}.sex_chroms.{}.".format(
					bam_path, args.sample_id, rg_id),
				fastq_files, args.cpus, rg_tag,
				[str(x).strip() for x in args.bwa_flags.split()])
			temp_bam_list.append(temp_bam)
	if len(temp_bam_list) < 2:
		new_bam = temp_bam_list[0]
	else:
		new_bam = bam.sambamba_merge(
			args.sambamba_path, temp_bam_list, "{}/{}.sex_chroms".format(
				bam_path, args.sample_id), args.cpus)
	return new_bam


def swap_sex_chroms(new_bam_file):
	merged_bam = bam.switch_sex_chromosomes_sambamba(
		args.samtools_path, args.sambamba_path, input_bam.filepath,
		new_bam_file.filepath, args.x_chromosome + args.y_chromosome,
		bam_path, args.sample_id, args.cpus, xyalign_params_dict)
	return merged_bam


def bam_analysis_postprocessing():
	"""
	Runs bam analyis part of pipeline for postprocessed bam files

	Returns 0
	"""
	# Depth/MAPQ
	if args.no_bam_analysis is not True:
		pass_df = []
		fail_df = []
		for chromosome in args.chromosomes:
			if args.window_size is not None and args.window_size != "None":
				data = final_bam.analyze_bam_fetch(
					chromosome, int(args.window_size))
			else:
				data = final_bam.analyze_bam_fetch(
					chromosome, None, args.target_bed)
			tup = utils.make_region_lists(
				data["windows"], args.mapq_cutoff, args.depth_filter)
			pass_df.append(tup[0])
			fail_df.append(tup[1])
			utils.plot_depth_mapq(
				data, depth_mapq_prefix_postprocessing, args.sample_id,
				final_bam.get_chrom_length(chromosome), args.marker_size,
				args.marker_transparency)
		utils.output_bed(output_bed_high_postprocessing, *pass_df)
		utils.output_bed(output_bed_low_postprocessing, *fail_df)

	# Platypus
	include_bed = output_bed_high_postprocessing
	if args.platypus_calling in ["both", "after"]:
		a = variants.platypus_caller(
			args.platypus_path, postprocessing_vcf_log, input_bam.filepath,
			ref.filepath, args.chromosomes, args.cpus, postprocessing_vcf,
			include_bed)
		if a != 0:
			logger.error("Error in platypus calling on {}".format(
				final_bam.filepath))
			sys.exit(1)
		if args.no_variant_plots is not True:
			variants.plot_variants_per_chrom(
				args.chromosomes, postprocessing_vcf,
				args.sample_id, readbalance_prefix_postprocessing,
				args.variant_quality_cutoff, args.marker_size,
				args.marker_transparency, final_bam)

	return(pass_df, fail_df)

if __name__ == "__main__":
	# Version - placeholder for now - need to incorporate it into __init__.py
	version = "0.1"
	citation = """
	XYalign: Inferring Sex Chromosome Ploidy in NGS Data

	Timothy H Webster, Tanya Phung, Madeline Couse, Bruno Grande, Eric Karlins,
	Phillip Richmond, Whitney Whitford, Melissa A. Wilson Sayres

	2016

	Version: {}
	""".format(version)

	# Start timer
	xyalign_start = time.time()

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

	# Initiate logging
	logger = logging.getLogger("xyalign")
	logger.setLevel(logging.DEBUG)
	# Create File Handler
	fh = logging.FileHandler(logfile, mode="w")
	fh.setLevel(logging.DEBUG)
	# Create Console Handler
	ch = logging.StreamHandler()
	if args.reporting_level == "DEBUG":
		ch.setLevel(logging.DEBUG)
	elif args.reporting_level == "INFO":
		ch.setLevel(logging.INFO)
	elif args.reporting_level == "ERROR":
		ch.setLevel(logging.ERROR)
	elif args.reporting_level == "CRITICAL":
		ch.setLevel(logging.CRITICAL)
	else:
		ch.setLevel(logging.INFO)
	# Set Formatter
	formatter = logging.Formatter(
		'%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	fh.setFormatter(formatter)
	ch.setFormatter(formatter)
	# Add handlers to logger
	logger.addHandler(fh)
	logger.addHandler(ch)

	# Log citation
	logger.info("{}".format(citation))

	# Set up param dictionary
	xyalign_params_dict = {'ID': 'XYalign', 'VN': version, 'CL': []}
	p = ""
	for arg in args.__dict__:
		p = p + "{}={}, ".format(arg, args.__dict__[arg])
		xyalign_params_dict['CL'].append("{}={}".format(arg, args.__dict__[arg]))

	# Log parameters and pipeline start
	logger.info("Parameters: {}".format(p))
	logger.info("Beginning XYalign")

	# Setup output paths
	fastq_path = os.path.join(args.output_dir, "fastq")
	bam_path = os.path.join(args.output_dir, "bam")
	reference_path = os.path.join(args.output_dir, "reference")
	bed_path = os.path.join(args.output_dir, "bed")
	vcf_path = os.path.join(args.output_dir, "vcf")
	plots_path = os.path.join(args.output_dir, "plots")
	results_path = os.path.join(args.output_dir, "results")

	# Create paths for output files
	# reference-related
	if args.xx_ref_out is not None:
		xx_out = os.path.join(reference_path, args.xx_ref_out)
	else:
		xx_out = os.path.join(reference_path, "xyalign_noY.masked.fa")
	if args.xy_ref_out is not None:
		xy_out = os.path.join(reference_path, args.xy_ref_out)
	else:
		xy_out = os.path.join(reference_path, "xyalign_withY.masked.fa")
	# variant/vcf related
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
	# Depth/mapq related
	depth_mapq_prefix_noprocessing = os.path.join(
		plots_path, "{}_noprocessing".format(args.sample_id))
	depth_mapq_prefix_postprocessing = os.path.join(
		plots_path, "{}_postprocessing".format(args.sample_id))
	# Bedfile related
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

	######################################
	############ Run XYalign #############
	######################################
	ref = reftools.RefFasta(args.ref, args.samtools_path, args.bwa_path)
	input_bam = bam.BamFile(args.bam, args.samtools_path)

	# Check to ensure bam and fasta are compatible and imports work
	if args.skip_compatibility_check is False:
		compatible = utils.check_bam_fasta_compatibility(input_bam, ref)
		if compatible is False:
			logger.error(
				"Exiting due to compatibility issues between {} and {}. Check: "
				"1) that this fasta was used when generating this bam, 2) that "
				"sequence lengths and names are identical between the two files. "
				"You can check 2) by comparing the bam header (e.g., "
				"samtools -H {}) with a sequence dictionary (.dict) created for "
				"{}.  If you think this is an error, you can use the flag "
				"--skip_compatibility_check.".format(
					input_bam.filepath, ref.filepath, input_bam.filepath,
					ref.filepath))
			logging.shutdown()
			sys.exit(1)

	# Reference Prep Only
	if args.PREPARE_REFERENCE is True:
		logger.info(
			"PREPARE_REFERENCE set, so only preparing reference fastas.")
		ref_prep()
		logger.info("PREPARE_REFERENCE complete.")
		logger.info("XYalign complete. Elapsed time: {} seconds".format(
			time.time() - xyalign_start))
		logging.shutdown()
		sys.exit(0)

	# Stats Only
	elif args.ANALYZE_BAM is True:
		logger.info(
			"ANALYZE_BAM set, so only running steps required "
			"for bam analysis.")
		bam_analysis_noprocessing()
		logger.info("ANALYZE_BAM complete.")
		logger.info("XYalign complete. Elapsed time: {} seconds".format(
			time.time() - xyalign_start))
		logging.shutdown()
		sys.exit(0)

	# Ploidy Estimation Only
	elif args.CHARACTERIZE_SEX_CHROMS is True:
		logger.info(
			"CHARACTERIZE_SEX_CHROMS set, so only running steps required "
			"for to characterize sex chromosome complement. Note that "
			"this involve both playtpus calling and bam analysis too.")
		bam_dfs = bam_analysis_noprocessing()
		ploidy_results = ploidy_analysis(bam_dfs[0], bam_dfs[1])
		logger.info("CHARACTERIZE_SEX_CHROMS complete.")
		logger.info("XYalign complete. Elapsed time: {} seconds".format(
			time.time() - xyalign_start))
		logging.shutdown()
		sys.exit(0)

	# Remapping Only
	elif args.REMAPPING is True:
		logger.info(
			"REMAPPING set, so only running steps required for remapping. "
			"Requires --y_present or --y_absent to be set")
		if args.y_present is True:
			y_present = True
		elif args.y_absent is True:
			y_present = False
		else:
			logger.error(
				"--y_present or --y_absent required for --REMAPPING. "
				"Exiting.")
			sys.exit(1)
		if args.xx_ref_in is None or args.xy_ref_in is None:
			logger.info(
				"Input masked reference not provided for both "
				"XX and XY mapping, so creating both")
			masked_refs = ref_prep()
		else:
			xx = reftools.RefFasta(
				args.xx_ref_in, args.samtools_path, args.bwa_path)
			xy = reftools.RefFasta(
				args.xy_ref_in, args.samtools_path, args.bwa_path)
			xx.conditional_index_bwa()
			xx.seq_dict()
			xy.conditional_index_bwa()
			xy.seq_dict()
			masked_refs = (xx, xy)
		sex_chrom_bam = bam.BamFile(remapping(), args.samtools_path)
		if args.sex_chrom_bam_only is True:
			final_bam = sex_chrom_bam
		else:
			final_bam = bam.BamFile(
				swap_sex_chroms(sex_chrom_bam), args.samtools_path)
		logger.info("REMAPPING complete.")
		logger.info("XYalign complete. Elapsed time: {} seconds".format(
			time.time() - xyalign_start))
		logging.shutdown()
		sys.exit(0)

	# Full Pipeline
	else:
		logger.info(
			"Running entire XYalign pipeline")
		if args.xx_ref_in is None or args.xy_ref_in is None:
			logger.info(
				"Input masked reference not provided for both "
				"XX and XY mapping, so creating both")
			masked_refs = ref_prep()
		else:
			xx = reftools.RefFasta(
				args.xx_ref_in, args.samtools_path, args.bwa_path)
			xy = reftools.RefFasta(
				args.xy_ref_in, args.samtools_path, args.bwa_path)
			xx.conditional_index_bwa()
			xx.seq_dict()
			xy.conditional_index_bwa()
			xy.seq_dict()
			masked_refs = (xx, xy)
		bam_dfs = bam_analysis_noprocessing()
		ploidy_results = ploidy_analysis(bam_dfs[0], bam_dfs[1])
		if args.y_present is True:
			y_present = True
		elif args.y_absent is True:
			y_present = False
		else:
			logger.error("Need to implement ploidy decision. Exiting.")
			sys.exit(1)
		sex_chrom_bam = bam.BamFile(remapping(), args.samtools_path)
		if args.sex_chrom_bam_only is True:
			final_bam = sex_chrom_bam
		else:
			final_bam = bam.BamFile(
				swap_sex_chroms(sex_chrom_bam), args.samtools_path)
		bam_analysis_postprocessing()
		logger.info("XYalign complete. Elapsed time: {} seconds".format(
			time.time() - xyalign_start))
		logging.shutdown()
		sys.exit(0)

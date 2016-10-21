from __future__ import division
import argparse
import os
import subprocess
import sys
from matplotlib import pyplot as plt
import pysam

def main():
	""" Main program"""
	
	args = parse_args()
	
	## First round of Platypus calling and plotting
	if args.platypus_calling == "both" or "before"
		a = platypus_caller(args.bam, args.ref, args.chromosomes, args.cpus, args.output_dir + "{}.noprocessing.vcf".format(args.sample_id))
		if a != 0:
			print "Error in initial Platypus calling."
			sys.exit(1)
		if no_variant_plots == True:
			plot_variants_per_chrom(args.chromosomes, args.output_dir + "{}.noprocessing.vcf".format(args.sample_id),
									args.sample_id, args.output_dir, args.variant_quality_cutoff,
									args.marker_size, margs.marker_transparency)
	
	## Analyze bam for depth and mapq and infer ploidy
	
	
	## Remapping
	
	
	## Final round of calling and plotting
									
			




		
	
def parse_args():
	"""Parse command-line arguments"""
	parser = argparse.ArgumentParser(description="XYalign.  A tool to estimate sex chromosome ploidy and use this information to correct mapping and variant calling on the sex chromosomes.")
	parser.add_argument("--bam", required=True,
						help="Input bam file.")
	parser.add_argument("--ref", required=True,
						help="Path to reference sequence (including file name).")
	parser.add_argument("--chromosomes", "-c", default=["chrX","chrY","chr19"],
						help="Chromosomes to analyze.")
	parser.add_argument("--sample_id", "-id" default="sample",
						help="Name/ID of sample - for use in plot titles and file naming.")
	parser.add_argument("--platypus_calling", default="both",
						help="Platypus calling withing the pipeline (before processing, after processing, both, or neither). Options: both, none, before, after.")
	parser.add_argument("--no_variant_plots", action="store_false", default=True,
						help="Include flag to prevent plotting read balance from VCF files.")
	parser.add_argument("--variant_quality_cutoff", "-vqc", type=int, default=20,
						help="Consider all SNPs with a quality greater than or equal to this value. Default is 20.")
	parser.add_argument("--marker_size", type=float, default=1.0,
						help="Marker size for genome-wide plots in matplotlib.")
	parser.add_argument("--marker_transparency", "-mt", type=float, default=0.5,
						help="Transparency of markers in genome-wide plots.  Alpha in matplotlib.")
	parser.add_argument("--output_dir", "-o",
						help="Output directory")
						
	args = parser.parse_args()
	
	#Validate arguments
	if not os.path.exists(args.output_dir):
		os.makedirs(args.output_dir)
	if args.platypus_calling not in ["both", "none", "before", "after"]:
		print "Error. Platypus calling must be "both", "none", "before", or "after". Default is "both"."
		sys.exit(1)
		
	# Return arguments namespace
	return args
	

def get_length(bamfile, chrom):
	""" Extract chromosome length from BAM header.
	
	args:
		bamfile: pysam AlignmentFile object
		chrom: chromosome name (string)
		
	returns:
		Length (int)
	
	"""

						
def platypus_caller(bam, ref, chroms, cpus, output_file):
	""" Uses platypus to make variant calls on provided bam file
	
	bam is input bam file
	ref is path to reference sequence
	chroms is a list of chromosomes to call on, e.g., ["chrX", "chrY", "chr19"]
	cpus is the number of threads/cores to use
	output_file is the name of the output vcf
	"""
	regions = ','.join(map(str,chroms))
	command_line = "platypus callVariants --bamFiles {} -o {} --refFile {} --nCPU {} --regions {} --assemble 1".format(bam, output_file, ref, cpus, regions)
	return_code = subprocess.call(command_line, shell=True)
	if return_code == 0:
		return True
	else:
		return None
		
def parse_platypus_VCF(filename, qualCutoff, chrom):
	""" Parse vcf generated by Platypus """
    infile = open("{}".format(filename),'r')
    positions = []
    quality = []
    readBalance = []
    for line in infile:
        if line[0] != chrom:
            continue
        cols=line.strip('\n').split('\t')
        pos = int(cols[1])
        qual = float(cols[5])
        if qual < qualCutoff:
            continue
        TR = cols[7].split(';')[17].split('=')[1]
        TC = cols[7].split(';')[14].split('=')[1]
        if ',' in TR or ',' in TC:
            continue
        if (float(TR)==0) or (float(TC) == 0):
            continue    
        ReadRatio = float(TR)/float(TC)
        
        # Add to arrays
        readBalance.append(ReadRatio)
        positions.append(pos)
        quality.append(qual)
        
	return (positions,quality,readBalance)
	
def plot_read_balance(chrom, positions, readBalance, sampleID, output_prefix, MarkerSize, MarkerAlpha, Xlim):
    """ Plots read balance at each SNP along a chromosome """
    if "x" in chrom.lower():
        Color="green"
    elif "y" in chrom.lower():
        Color = "blue"
    else:
    	Color = "red"
    fig = plt.figure(figsize=(15,5))
    axes = fig.add_subplot(111)
    axes.scatter(positions,readBalance,c=Color,alpha=MarkerAlpha,s=MarkerSize,lw=0)
    axes.set_xlim(0,Xlim)
    axes.set_title(sampleID)
    axes.set_xlabel("Chromosomal Coordinate")
    axes.set_ylabel("Read Balance")
    #print(len(positions))
    plt.savefig("{}_{}_ReadBalance_GenomicScatter.svg".format(output_prefix, chrom))
    plt.savefig("{}_{}_ReadBalance_GenomicScatter.png".format(output_prefix, chrom))
	#plt.show()
	
def hist_read_balance(chrom, readBalance, sampleID, output_prefix):
    """ Plot a histogram of read balance """
    if "x" in chrom.lower():
        Color="green"
    elif "y" in chrom.lower():
        Color = "blue"
    else:
    	Color = "red"
    fig = plt.figure(figsize=(8,8))
    axes = fig.add_subplot(111)
    axes.set_title(sampleID)
    axes.set_xlabel("Read Balance")
    axes.set_ylabel("Frequency")
    axes.hist(readBalance,bins=50,color=Color)
    plt.savefig("{}_{}_ReadBalance_Hist.svg".format(output_prefix, chrom))
    plt.savefig("{}_{}_ReadBalance_Hist.png".format(output_prefix, chrom))
	#plt.show()

def plot_variants_per_chrom(chrom_list, vcf_file, sampleID, output_prefix, qualCutoff, MarkerSize, MarkerAlpha):
	for i in chrom_list:
		parse_results = parse_platypus_VCF(args.output_dir + "{}.noprocessing.vcf".format(sampleID), qualCutoff, i)
		plot_read_balance(i, parse_results[0], parse_results[1], sampleID, output_directory + "{}.noprocessing".format(sampleID), MarkerSize, MarkerAlpha, get_length(pysam.AlignmentFile(args.bam, b), i))
		hist_read_balance(i, readBalance, sampleID, output_prefix)
	pass
	
if __name__ == "__main__":
	main()
	

	
using System;
using System.IO;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Collections.Generic;

namespace RosRedemptionIcon {
    public class Program {
        public static void Main(string[] args) {
            Console.WriteLine("[INFO] Generating ROS Redemption custom game icons...");
            
            int[] sizes = new int[] { 256, 128, 64, 48, 32, 16 };
            List<byte[]> pngImages = new List<byte[]>();

            foreach (int size in sizes) {
                using (var bmp = DrawEmblem(size)) {
                    using (var ms = new MemoryStream()) {
                        bmp.Save(ms, ImageFormat.Png);
                        pngImages.Add(ms.ToArray());
                    }
                }
            }

            byte[] icoBytes = BuildIco(sizes, pngImages);

            string target1 = @"C:\DieHardROS\res\ros.ico";
            string target2 = @"C:\DieHardROS\logo.ico";
            string target3 = @"c:\Users\seanj\dev\ros_redemption\ros_redemption.ico";
            string targetPng = @"C:\DieHardROS\res\ros_redemption.png";

            // Save primary 256 PNG preview as well
            File.WriteAllBytes(targetPng, pngImages[0]);
            File.WriteAllBytes(target1, icoBytes);
            File.WriteAllBytes(target2, icoBytes);
            File.WriteAllBytes(target3, icoBytes);

            Console.WriteLine("[SUCCESS] Generated ROS Redemption .ico files at:");
            Console.WriteLine(" - " + target1);
            Console.WriteLine(" - " + target2);
            Console.WriteLine(" - " + target3);
        }

        public static Bitmap DrawEmblem(int size) {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp)) {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;

                float s = size / 256f;

                // Dark Metallic Shield Base
                var shieldPath = new GraphicsPath();
                shieldPath.AddPolygon(new PointF[] {
                    new PointF(128 * s, 10 * s),
                    new PointF(235 * s, 45 * s),
                    new PointF(225 * s, 170 * s),
                    new PointF(128 * s, 245 * s),
                    new PointF(31 * s, 170 * s),
                    new PointF(21 * s, 45 * s)
                });

                // Outer Glow / Border
                using (var penGlow = new Pen(Color.FromArgb(200, 255, 71, 87), 8 * s)) {
                    g.DrawPath(penGlow, shieldPath);
                }

                // Dark Shield Body Gradient
                using (var brush = new LinearGradientBrush(new RectangleF(0, 0, size, size),
                    Color.FromArgb(255, 18, 24, 38), Color.FromArgb(255, 8, 10, 16), 45f)) {
                    g.FillPath(brush, shieldPath);
                }

                // Inner Crimson & Gold Trim
                var innerPath = new GraphicsPath();
                innerPath.AddPolygon(new PointF[] {
                    new PointF(128 * s, 26 * s),
                    new PointF(218 * s, 56 * s),
                    new PointF(210 * s, 162 * s),
                    new PointF(128 * s, 228 * s),
                    new PointF(46 * s, 162 * s),
                    new PointF(38 * s, 56 * s)
                });

                using (var penGold = new Pen(Color.FromArgb(255, 255, 165, 2), 3 * s)) {
                    g.DrawPath(penGold, innerPath);
                }

                // Center Skull / Tactical Helmet Silhouette
                // Forehead / Visor
                using (var brushRed = new SolidBrush(Color.FromArgb(255, 255, 71, 87))) {
                    // Angular tactical visor
                    var visor = new GraphicsPath();
                    visor.AddPolygon(new PointF[] {
                        new PointF(65 * s, 105 * s),
                        new PointF(128 * s, 125 * s),
                        new PointF(191 * s, 105 * s),
                        new PointF(185 * s, 130 * s),
                        new PointF(128 * s, 148 * s),
                        new PointF(71 * s, 130 * s)
                    });
                    g.FillPath(brushRed, visor);

                    // Visor glow
                    using (var penCrimson = new Pen(Color.FromArgb(255, 255, 220, 220), 2 * s)) {
                        g.DrawPath(penCrimson, visor);
                    }
                }

                // Crown / Wings (Top Crest)
                using (var penAccent = new Pen(Color.FromArgb(255, 255, 71, 87), 4 * s)) {
                    g.DrawLine(penAccent, 60 * s, 50 * s, 128 * s, 75 * s);
                    g.DrawLine(penAccent, 128 * s, 75 * s, 196 * s, 50 * s);
                }

                // Tactical "R" Emblem (Redemption Monogram)
                if (size >= 32) {
                    using (var font = new Font("Arial Black", 44 * s, FontStyle.Bold)) {
                        using (var textBrush = new SolidBrush(Color.FromArgb(240, 255, 255, 255))) {
                            var sf = new StringFormat();
                            sf.Alignment = StringAlignment.Center;
                            sf.LineAlignment = StringAlignment.Center;
                            g.DrawString("R", font, textBrush, new RectangleF(0, 52 * s, size, 80 * s), sf);
                        }
                    }
                }

                // Bottom banner: "REDEMPTION"
                if (size >= 48) {
                    var bannerPath = new GraphicsPath();
                    bannerPath.AddPolygon(new PointF[] {
                        new PointF(35 * s, 172 * s),
                        new PointF(221 * s, 172 * s),
                        new PointF(210 * s, 198 * s),
                        new PointF(128 * s, 215 * s),
                        new PointF(46 * s, 198 * s)
                    });
                    using (var bannerBrush = new SolidBrush(Color.FromArgb(240, 180, 20, 30))) {
                        g.FillPath(bannerBrush, bannerPath);
                    }
                    using (var penBanner = new Pen(Color.FromArgb(255, 255, 165, 2), 2 * s)) {
                        g.DrawPath(penBanner, bannerPath);
                    }

                    using (var fontSmall = new Font("Segoe UI", 12 * s, FontStyle.Bold)) {
                        using (var textBrush = new SolidBrush(Color.White)) {
                            var sf = new StringFormat();
                            sf.Alignment = StringAlignment.Center;
                            sf.LineAlignment = StringAlignment.Center;
                            g.DrawString("REDEMPTION", fontSmall, textBrush, new RectangleF(0, 176 * s, size, 24 * s), sf);
                        }
                    }
                }
            }
            return bmp;
        }

        public static byte[] BuildIco(int[] sizes, List<byte[]> pngs) {
            using (var ms = new MemoryStream()) {
                using (var bw = new BinaryWriter(ms)) {
                    // Header: Reserved (0), Type (1 = ICO), Count
                    bw.Write((ushort)0);
                    bw.Write((ushort)1);
                    bw.Write((ushort)sizes.Length);

                    int offset = 6 + (16 * sizes.Length);

                    for (int i = 0; i < sizes.Length; i++) {
                        int sz = sizes[i];
                        byte[] data = pngs[i];

                        bw.Write((byte)(sz >= 256 ? 0 : sz)); // Width
                        bw.Write((byte)(sz >= 256 ? 0 : sz)); // Height
                        bw.Write((byte)0); // Color count
                        bw.Write((byte)0); // Reserved
                        bw.Write((ushort)1); // Color planes
                        bw.Write((ushort)32); // Bits per pixel
                        bw.Write((uint)data.Length); // Image size
                        bw.Write((uint)offset); // Offset

                        offset += data.Length;
                    }

                    for (int i = 0; i < pngs.Count; i++) {
                        bw.Write(pngs[i]);
                    }
                }
                return ms.ToArray();
            }
        }
    }
}

